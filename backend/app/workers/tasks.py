import asyncio
from datetime import UTC, datetime
from uuid import UUID

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from sqlalchemy import select

from app.agents.graph import build_research_graph
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.research import (
    ApprovalRequest,
    ApprovalStatus,
    ResearchRun,
    RunStatus,
)
from app.services.events import publish_event
from app.services.execution_control import (
    RunCancelled,
    RunTimedOut,
    check_run_control,
)
from app.workers.celery_app import celery_app

settings = get_settings()

_worker_event_loop: asyncio.AbstractEventLoop | None = None


def get_worker_event_loop() -> asyncio.AbstractEventLoop:
    """
    Maintain one persistent event loop per Celery worker process.

    asyncpg connections are attached to the loop that created them.
    Reusing one loop prevents cross-loop pooled connection errors.
    """
    global _worker_event_loop

    if (
        _worker_event_loop is None
        or _worker_event_loop.is_closed()
    ):
        _worker_event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_event_loop)

    return _worker_event_loop


async def _load_run(run_id: str) -> ResearchRun:
    async with SessionLocal() as session:
        run = await session.get(
            ResearchRun,
            UUID(run_id),
        )

        if run is None:
            raise ValueError(
                f"Unknown research run: {run_id}"
            )

        return run


async def _execute(
    run_id: str,
    resume: dict | None = None,
) -> None:
    run = await _load_run(run_id)

    config = {
        "configurable": {
            "thread_id": run.thread_id,
        }
    }

    try:
        await check_run_control(run.id)

        async with SessionLocal() as session:
            managed_run = await session.get(
                ResearchRun,
                run.id,
                with_for_update=True,
            )

            if managed_run.status in {
                RunStatus.CANCELLED,
                RunStatus.TIMED_OUT,
            }:
                return

            managed_run.status = RunStatus.RUNNING
            managed_run.error = None
            await session.commit()

        await publish_event(
            run_id,
            "run.started",
            {"run_id": run_id},
        )

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
                    "trace_id": run_id,
                    "query": run.query,
                    "budget_usd": float(run.budget_usd),
                    "evidence": [],
                }
            )

            result = await graph.ainvoke(
                graph_input,
                config=config,
            )

        async with SessionLocal() as session:
            managed_run = await session.get(
                ResearchRun,
                run.id,
                with_for_update=True,
            )

            # A concurrent cancellation or deadline must not be
            # overwritten by a late graph result.
            if managed_run.status in {
                RunStatus.CANCELLED,
                RunStatus.TIMED_OUT,
            }:
                return

            if "__interrupt__" in result:
                interrupt_data = (
                    result["__interrupt__"][0].value
                )

                managed_run.status = (
                    RunStatus.WAITING_APPROVAL
                )
                managed_run.plan = {
                    "items": result.get("plan", [])
                }

                existing = await session.scalar(
                    select(ApprovalRequest).where(
                        ApprovalRequest.run_id
                        == managed_run.id,
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

                await publish_event(
                    run_id,
                    "approval.required",
                    interrupt_data,
                )

                return

            managed_run.status = (
                RunStatus.CANCELLED
                if result.get("status") == "cancelled"
                else RunStatus.COMPLETED
            )
            managed_run.finished_at = datetime.now(UTC)

            if managed_run.status == RunStatus.CANCELLED:
                managed_run.cancellation_requested_at = (
                    datetime.now(UTC)
                )
                managed_run.cancellation_reason = (
                    "Research plan was rejected"
                )

            managed_run.result = result.get("report")
            await session.commit()

        if run.deadline_task_id:
            celery_app.control.revoke(
                run.deadline_task_id,
                terminate=False,
            )

        event_type = (
            "run.cancelled"
            if result.get("status") == "cancelled"
            else "run.completed"
        )

        await publish_event(
            run_id,
            event_type,
            {"status": result.get("status")},
        )

    except (RunCancelled, RunTimedOut) as exc:
        now = datetime.now(UTC)

        async with SessionLocal() as session:
            managed_run = await session.get(
                ResearchRun,
                run.id,
            )

            managed_run.status = exc.terminal_status
            managed_run.finished_at = (
                managed_run.finished_at or now
            )
            managed_run.error = (
                str(exc)
                if isinstance(exc, RunTimedOut)
                else None
            )

            await session.commit()

        event_type = (
            "run.timed_out"
            if isinstance(exc, RunTimedOut)
            else "run.cancelled"
        )

        await publish_event(
            run_id,
            event_type,
            {
                "run_id": run_id,
                "reason": str(exc),
                "finished_at": now.isoformat(),
            },
        )

        return

    except Exception as exc:
        async with SessionLocal() as session:
            managed_run = await session.get(
                ResearchRun,
                run.id,
                with_for_update=True,
            )

            if managed_run.status in {
                RunStatus.CANCELLED,
                RunStatus.TIMED_OUT,
            }:
                return

            managed_run.status = RunStatus.FAILED
            managed_run.error = str(exc)[:4000]
            managed_run.finished_at = datetime.now(UTC)

            await session.commit()

        await publish_event(
            run_id,
            "run.failed",
            {"error": str(exc)},
        )

        raise


async def _enforce_deadline(run_id: str) -> None:
    run_uuid = UUID(run_id)

    async with SessionLocal() as session:
        run = await session.get(
            ResearchRun,
            run_uuid,
            with_for_update=True,
        )

        if run is None or run.status in {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.TIMED_OUT,
        }:
            return

        now = datetime.now(UTC)

        if run.deadline_at > now:
            return

        run.status = RunStatus.TIMED_OUT
        run.finished_at = now
        run.error = "Research run deadline exceeded"

        execution_task_id = run.celery_task_id
        deadline_at = run.deadline_at

        await session.commit()

    if execution_task_id:
        celery_app.control.revoke(
            execution_task_id,
            terminate=False,
        )

    await publish_event(
        run_id,
        "run.timed_out",
        {
            "run_id": run_id,
            "deadline_at": deadline_at.isoformat(),
        },
    )


@celery_app.task(
    name="research.execute",
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def execute_research(
    run_id: str,
    resume: dict | None = None,
) -> None:
    loop = get_worker_event_loop()
    loop.run_until_complete(
        _execute(run_id, resume)
    )


@celery_app.task(name="research.enforce_deadline")
def enforce_research_deadline(run_id: str) -> None:
    loop = get_worker_event_loop()
    loop.run_until_complete(
        _enforce_deadline(run_id)
    )