import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.deps import DbSession
from app.core.config import get_settings
from app.models.evidence import EvidenceItem, LLMCall, Source, ToolExecution
from app.models.evaluation import ResearchEvaluation
from app.models.report import CitationValidation, ReportCitation, ResearchReport
from app.models.research import (
    ApprovalRequest,
    ApprovalStatus,
    ResearchRun,
    RunStatus,
)
from app.models.review import (
    Contradiction,
    CoverageAssessment,
    CriticReview,
    ResearchGap,
)
from app.models.trace import ExecutionTrace
from app.schemas.evaluation import (
    ExecutionTraceRead,
    ResearchEvaluationRead,
)
from app.schemas.report import (
    CitationValidationRead,
    ReportCitationRead,
    ResearchReportRead,
)
from app.schemas.research import (
    ApprovalDecision,
    ApprovalRead,
    CancellationRequest,
    ContradictionRead,
    CoverageRead,
    CriticReviewRead,
    EvidenceRead,
    ResearchGapRead,
    ResearchRunCreate,
    ResearchRunRead,
    SourceRead,
    UsageSummary,
)
from app.services.events import publish_event, stream_events
from app.workers.celery_app import celery_app
from app.workers.tasks import (
    enforce_research_deadline,
    execute_research,
)

router = APIRouter(prefix="/research", tags=["research"])
settings = get_settings()


async def _revoke_task(task_id: str | None) -> None:
    if task_id:
        await asyncio.to_thread(
            celery_app.control.revoke,
            task_id,
            terminate=False,
        )


@router.post(
    "/runs",
    response_model=ResearchRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_run(
    payload: ResearchRunCreate,
    session: DbSession,
) -> ResearchRun:
    timeout_seconds = (
        payload.timeout_seconds
        or settings.research_default_timeout_seconds
    )
    timeout_seconds = min(
        timeout_seconds,
        settings.research_max_timeout_seconds,
    )

    now = datetime.now(UTC)

    run = ResearchRun(
        thread_id=str(uuid4()),
        query=payload.query,
        status=RunStatus.QUEUED,
        budget_usd=(
            payload.budget_usd
            or Decimal(str(settings.research_default_budget_usd))
        ),
        deadline_at=now + timedelta(seconds=timeout_seconds),
    )

    session.add(run)
    await session.commit()
    await session.refresh(run)

    execution_task = execute_research.delay(str(run.id))
    deadline_task = enforce_research_deadline.apply_async(
        args=[str(run.id)],
        countdown=timeout_seconds,
    )

    run.celery_task_id = execution_task.id
    run.deadline_task_id = deadline_task.id

    await session.commit()
    await session.refresh(run)

    await publish_event(
        str(run.id),
        "run.queued",
        {
            "run_id": str(run.id),
            "deadline_at": run.deadline_at.isoformat(),
        },
    )

    return run


@router.get(
    "/runs/{run_id}",
    response_model=ResearchRunRead,
)
async def get_run(
    run_id: UUID,
    session: DbSession,
) -> ResearchRun:
    run = await session.get(ResearchRun, run_id)

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="Research run not found",
        )

    terminal_statuses = {
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.TIMED_OUT,
    }

    if (
        run.status not in terminal_statuses
        and run.deadline_at <= datetime.now(UTC)
    ):
        run.status = RunStatus.TIMED_OUT
        run.finished_at = datetime.now(UTC)
        run.error = "Research run deadline exceeded"

        await session.commit()
        await session.refresh(run)

        await _revoke_task(run.celery_task_id)

        await publish_event(
            str(run.id),
            "run.timed_out",
            {"run_id": str(run.id)},
        )

    return run


@router.get(
    "/runs/{run_id}/approval",
    response_model=ApprovalRead,
)
async def get_approval(
    run_id: UUID,
    session: DbSession,
) -> ApprovalRequest:
    approval = await session.scalar(
        select(ApprovalRequest)
        .where(ApprovalRequest.run_id == run_id)
        .order_by(ApprovalRequest.created_at.desc())
    )

    if approval is None:
        raise HTTPException(
            status_code=404,
            detail="No approval request for this run",
        )

    return approval


@router.post(
    "/runs/{run_id}/approval",
    response_model=ApprovalRead,
)
async def decide_approval(
    run_id: UUID,
    payload: ApprovalDecision,
    session: DbSession,
) -> ApprovalRequest:
    run = await session.get(ResearchRun, run_id)

    approval = await session.scalar(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.run_id == run_id,
            ApprovalRequest.status == ApprovalStatus.PENDING,
        )
        .order_by(ApprovalRequest.created_at.desc())
    )

    if run is None or approval is None:
        raise HTTPException(
            status_code=404,
            detail="Pending approval not found",
        )

    if (
        run.status != RunStatus.WAITING_APPROVAL
        or approval.status != ApprovalStatus.PENDING
    ):
        raise HTTPException(
            status_code=409,
            detail="Approval has already been decided",
        )

    if run.deadline_at <= datetime.now(UTC):
        run.status = RunStatus.TIMED_OUT
        run.finished_at = datetime.now(UTC)
        run.error = "Research run deadline exceeded"

        await session.commit()

        await publish_event(
            str(run.id),
            "run.timed_out",
            {"run_id": str(run.id)},
        )

        raise HTTPException(
            status_code=409,
            detail="Research run deadline exceeded",
        )

    approval.status = payload.decision
    approval.decision_note = payload.note
    approval.decided_at = datetime.now(UTC)
    run.status = RunStatus.QUEUED

    await session.commit()
    await session.refresh(approval)

    task = execute_research.delay(
        str(run.id),
        {
            "decision": payload.decision,
            "note": payload.note or "",
        },
    )

    run.celery_task_id = task.id
    await session.commit()

    return approval


@router.post(
    "/runs/{run_id}/cancel",
    response_model=ResearchRunRead,
)
async def cancel_run(
    run_id: UUID,
    payload: CancellationRequest,
    session: DbSession,
) -> ResearchRun:
    run = await session.get(
        ResearchRun,
        run_id,
        with_for_update=True,
    )

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="Research run not found",
        )

    if run.status == RunStatus.CANCELLED:
        return run

    if run.status in {
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.TIMED_OUT,
    }:
        raise HTTPException(
            status_code=409,
            detail=f"Run is already {run.status}",
        )

    now = datetime.now(UTC)

    run.status = RunStatus.CANCELLED
    run.cancellation_requested_at = now
    run.cancellation_reason = payload.reason
    run.finished_at = now

    pending_approvals = list(
        await session.scalars(
            select(ApprovalRequest).where(
                ApprovalRequest.run_id == run_id,
                ApprovalRequest.status == ApprovalStatus.PENDING,
            )
        )
    )

    for approval in pending_approvals:
        approval.status = ApprovalStatus.REJECTED
        approval.decision_note = payload.reason
        approval.decided_at = now

    await session.commit()
    await session.refresh(run)

    await publish_event(
        str(run.id),
        "run.cancellation_requested",
        {
            "run_id": str(run.id),
            "reason": payload.reason,
        },
    )

    await _revoke_task(run.celery_task_id)
    await _revoke_task(run.deadline_task_id)

    await publish_event(
        str(run.id),
        "run.cancelled",
        {
            "run_id": str(run.id),
            "reason": payload.reason,
            "cancelled_at": now.isoformat(),
        },
    )

    return run


@router.get("/runs/{run_id}/events")
async def get_events(
    run_id: UUID,
    last_event_id: str = Header(default="0-0"),
) -> StreamingResponse:
    return StreamingResponse(
        stream_events(str(run_id), last_event_id),
        media_type="text/event-stream",
    )


@router.get(
    "/runs/{run_id}/sources",
    response_model=list[SourceRead],
)
async def list_sources(
    run_id: UUID,
    session: DbSession,
) -> list[Source]:
    if await session.get(ResearchRun, run_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Research run not found",
        )

    return list(
        await session.scalars(
            select(Source)
            .where(Source.run_id == run_id)
            .order_by(Source.quality_score.desc())
        )
    )


@router.get(
    "/runs/{run_id}/evidence",
    response_model=list[EvidenceRead],
)
async def list_evidence(
    run_id: UUID,
    session: DbSession,
) -> list[EvidenceItem]:
    if await session.get(ResearchRun, run_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Research run not found",
        )

    return list(
        await session.scalars(
            select(EvidenceItem)
            .where(EvidenceItem.run_id == run_id)
            .order_by(EvidenceItem.relevance_score.desc())
        )
    )


@router.get(
    "/runs/{run_id}/usage",
    response_model=UsageSummary,
)
async def get_usage(
    run_id: UUID,
    session: DbSession,
) -> UsageSummary:
    if await session.get(ResearchRun, run_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Research run not found",
        )

    tool_calls = await session.scalar(
        select(func.count())
        .select_from(ToolExecution)
        .where(ToolExecution.run_id == run_id)
    )

    llm_row = (
        await session.execute(
            select(
                func.count(LLMCall.id),
                func.coalesce(func.sum(LLMCall.input_tokens), 0),
                func.coalesce(func.sum(LLMCall.output_tokens), 0),
                func.coalesce(
                    func.sum(LLMCall.estimated_cost_usd),
                    0,
                ),
            ).where(LLMCall.run_id == run_id)
        )
    ).one()

    tool_cost = await session.scalar(
        select(
            func.coalesce(
                func.sum(ToolExecution.estimated_cost_usd),
                0,
            )
        ).where(ToolExecution.run_id == run_id)
    )

    return UsageSummary(
        tool_calls=tool_calls or 0,
        llm_calls=llm_row[0],
        input_tokens=llm_row[1],
        output_tokens=llm_row[2],
        estimated_cost_usd=(
            Decimal(str(tool_cost))
            + Decimal(str(llm_row[3]))
        ),
    )


async def _require_run(
    run_id: UUID,
    session: DbSession,
) -> None:
    if await session.get(ResearchRun, run_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Research run not found",
        )


@router.get(
    "/runs/{run_id}/coverage",
    response_model=list[CoverageRead],
)
async def list_coverage(
    run_id: UUID,
    session: DbSession,
) -> list[CoverageAssessment]:
    await _require_run(run_id, session)

    return list(
        await session.scalars(
            select(CoverageAssessment)
            .where(CoverageAssessment.run_id == run_id)
            .order_by(
                CoverageAssessment.iteration,
                CoverageAssessment.question_id,
            )
        )
    )


@router.get(
    "/runs/{run_id}/gaps",
    response_model=list[ResearchGapRead],
)
async def list_gaps(
    run_id: UUID,
    session: DbSession,
) -> list[ResearchGap]:
    await _require_run(run_id, session)

    return list(
        await session.scalars(
            select(ResearchGap)
            .where(ResearchGap.run_id == run_id)
            .order_by(
                ResearchGap.iteration,
                ResearchGap.question_id,
            )
        )
    )


@router.get(
    "/runs/{run_id}/contradictions",
    response_model=list[ContradictionRead],
)
async def list_contradictions(
    run_id: UUID,
    session: DbSession,
) -> list[Contradiction]:
    await _require_run(run_id, session)

    return list(
        await session.scalars(
            select(Contradiction)
            .where(Contradiction.run_id == run_id)
            .order_by(Contradiction.iteration)
        )
    )


@router.get(
    "/runs/{run_id}/critic",
    response_model=list[CriticReviewRead],
)
async def list_critic_reviews(
    run_id: UUID,
    session: DbSession,
) -> list[CriticReview]:
    await _require_run(run_id, session)

    return list(
        await session.scalars(
            select(CriticReview)
            .where(CriticReview.run_id == run_id)
            .order_by(CriticReview.iteration)
        )
    )


@router.get(
    "/runs/{run_id}/report",
    response_model=ResearchReportRead,
)
async def get_report(
    run_id: UUID,
    session: DbSession,
) -> ResearchReport:
    await _require_run(run_id, session)

    report = await session.scalar(
        select(ResearchReport).where(
            ResearchReport.run_id == run_id
        )
    )

    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Report has not been generated",
        )

    return report


@router.get(
    "/runs/{run_id}/report/citations",
    response_model=list[ReportCitationRead],
)
async def list_report_citations(
    run_id: UUID,
    session: DbSession,
) -> list[ReportCitation]:
    report = await session.scalar(
        select(ResearchReport).where(
            ResearchReport.run_id == run_id
        )
    )

    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Report has not been generated",
        )

    return list(
        await session.scalars(
            select(ReportCitation)
            .where(ReportCitation.report_id == report.id)
            .order_by(ReportCitation.marker)
        )
    )


@router.get(
    "/runs/{run_id}/report/validations",
    response_model=list[CitationValidationRead],
)
async def list_report_validations(
    run_id: UUID,
    session: DbSession,
) -> list[CitationValidation]:
    report = await session.scalar(
        select(ResearchReport).where(
            ResearchReport.run_id == run_id
        )
    )

    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Report has not been generated",
        )

    return list(
        await session.scalars(
            select(CitationValidation)
            .where(CitationValidation.report_id == report.id)
            .order_by(CitationValidation.attempt)
        )
    )


@router.get(
    "/runs/{run_id}/traces",
    response_model=list[ExecutionTraceRead],
)
async def list_execution_traces(
    run_id: UUID,
    session: DbSession,
) -> list[ExecutionTrace]:
    await _require_run(run_id, session)

    return list(
        await session.scalars(
            select(ExecutionTrace)
            .where(ExecutionTrace.run_id == run_id)
            .order_by(ExecutionTrace.started_at)
        )
    )


@router.get(
    "/runs/{run_id}/evaluation",
    response_model=ResearchEvaluationRead,
)
async def get_evaluation(
    run_id: UUID,
    session: DbSession,
) -> ResearchEvaluation:
    await _require_run(run_id, session)

    evaluation = await session.scalar(
        select(ResearchEvaluation).where(
            ResearchEvaluation.run_id == run_id
        )
    )

    if evaluation is None:
        raise HTTPException(
            status_code=404,
            detail="Evaluation has not been generated",
        )

    return evaluation