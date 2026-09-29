import asyncio
from uuid import UUID

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from sqlalchemy import select

from app.agents.graph import build_research_graph
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.research import ApprovalRequest, ApprovalStatus, ResearchRun, RunStatus
from app.services.events import publish_event
from app.workers.celery_app import celery_app

settings = get_settings()

_worker_event_loop: asyncio.AbstractEventLoop | None = None


def get_worker_event_loop() -> asyncio.AbstractEventLoop:
    """Return one persistent asyncio loop per Celery worker process."""
    global _worker_event_loop

    if _worker_event_loop is None or _worker_event_loop.is_closed():
        _worker_event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_event_loop)

    return _worker_event_loop


async def _load_run(run_id: str) -> ResearchRun:
    async with SessionLocal() as session:
        run = await session.get(ResearchRun, UUID(run_id))
        if run is None:
            raise ValueError(f"Unknown research run: {run_id}")
        return run


async def _execute(run_id: str, resume: dict | None = None) -> None:
    run = await _load_run(run_id)
    config = {"configurable": {"thread_id": run.thread_id}}

    async with SessionLocal() as session:
        managed_run = await session.get(ResearchRun, run.id)
        managed_run.status = RunStatus.RUNNING
        managed_run.error = None
        await session.commit()
    await publish_event(run_id, "run.started", {"run_id": run_id})

    try:
        async with AsyncPostgresSaver.from_conn_string(
            settings.langgraph_database_url
        ) as checkpointer:
            await checkpointer.setup()
            graph = build_research_graph(checkpointer)
            graph_input = (
                Command(resume=resume)
                if resume is not None
                else {
                    "run_id": run_id,
                    "query": run.query,
                    "budget_usd": float(run.budget_usd),
                    "evidence": [],
                }
            )
            result = await graph.ainvoke(graph_input, config=config)

        async with SessionLocal() as session:
            managed_run = await session.get(ResearchRun, run.id)
            if "__interrupt__" in result:
                interrupt_data = result["__interrupt__"][0].value
                managed_run.status = RunStatus.WAITING_APPROVAL
                managed_run.plan = {"items": result.get("plan", [])}
                existing = await session.scalar(
                    select(ApprovalRequest).where(
                        ApprovalRequest.run_id == managed_run.id,
                        ApprovalRequest.status
                        == ApprovalStatus.PENDING,
                    )
                )
                if existing is None:
                    session.add(
                        ApprovalRequest(
                            run_id=managed_run.id,
                            reason=interrupt_data["message"],
                            status=ApprovalStatus.PENDING,
                        )
                    )
                await session.commit()
                await publish_event(run_id, "approval.required", interrupt_data)
                return

            managed_run.status = (
                RunStatus.CANCELLED if result.get("status") == "cancelled" else RunStatus.COMPLETED
            )
            managed_run.result = result.get("report")
            await session.commit()
        await publish_event(run_id, "run.completed", {"status": result.get("status")})
    except Exception as exc:
        async with SessionLocal() as session:
            managed_run = await session.get(ResearchRun, run.id)
            managed_run.status = RunStatus.FAILED
            managed_run.error = str(exc)[:4000]
            await session.commit()
        await publish_event(run_id, "run.failed", {"error": str(exc)})
        raise


@celery_app.task(
    name="research.execute",
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def execute_research(run_id: str, resume: dict | None = None) -> None:
    loop = get_worker_event_loop()
    loop.run_until_complete(_execute(run_id, resume))
