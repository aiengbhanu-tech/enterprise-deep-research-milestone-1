from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.deps import DbSession
from app.core.config import get_settings
from app.models.evidence import EvidenceItem, LLMCall, Source, ToolExecution
from app.models.research import ApprovalRequest, ApprovalStatus, ResearchRun, RunStatus
from app.models.report import CitationValidation, ReportCitation, ResearchReport
from app.models.review import Contradiction, CoverageAssessment, CriticReview, ResearchGap
from app.schemas.research import (
    ApprovalDecision,
    ApprovalRead,
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
from app.schemas.report import CitationValidationRead, ReportCitationRead, ResearchReportRead
from app.services.events import stream_events
from app.workers.tasks import execute_research

router = APIRouter(prefix="/research", tags=["research"])
settings = get_settings()


@router.post("/runs", response_model=ResearchRunRead, status_code=status.HTTP_202_ACCEPTED)
async def create_run(payload: ResearchRunCreate, session: DbSession) -> ResearchRun:
    run = ResearchRun(
        thread_id=str(uuid4()),
        query=payload.query,
        status=RunStatus.QUEUED,
        budget_usd=payload.budget_usd or Decimal(str(settings.research_default_budget_usd)),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    execute_research.delay(str(run.id))
    return run


@router.get("/runs/{run_id}", response_model=ResearchRunRead)
async def get_run(run_id: UUID, session: DbSession) -> ResearchRun:
    run = await session.get(ResearchRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    return run


@router.get("/runs/{run_id}/approval", response_model=ApprovalRead)
async def get_approval(run_id: UUID, session: DbSession) -> ApprovalRequest:
    approval = await session.scalar(
        select(ApprovalRequest)
        .where(ApprovalRequest.run_id == run_id)
        .order_by(ApprovalRequest.created_at.desc())
    )
    if approval is None:
        raise HTTPException(status_code=404, detail="No approval request for this run")
    return approval


@router.post("/runs/{run_id}/approval", response_model=ApprovalRead)
async def decide_approval(
    run_id: UUID, payload: ApprovalDecision, session: DbSession
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
        raise HTTPException(status_code=404, detail="Pending approval not found")
    if run.status != RunStatus.WAITING_APPROVAL or approval.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=409, detail="Approval has already been decided")

    approval.status = payload.decision
    approval.decision_note = payload.note
    approval.decided_at = datetime.now(UTC)
    run.status = RunStatus.QUEUED
    await session.commit()
    await session.refresh(approval)
    execute_research.delay(str(run.id), {"decision": payload.decision, "note": payload.note or ""})
    return approval


@router.get("/runs/{run_id}/events")
async def get_events(run_id: UUID, last_event_id: str = Header(default="0-0")) -> StreamingResponse:
    return StreamingResponse(
        stream_events(str(run_id), last_event_id), media_type="text/event-stream"
    )


@router.get("/runs/{run_id}/sources", response_model=list[SourceRead])
async def list_sources(run_id: UUID, session: DbSession) -> list[Source]:
    if await session.get(ResearchRun, run_id) is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    return list(
        await session.scalars(
            select(Source).where(Source.run_id == run_id).order_by(Source.quality_score.desc())
        )
    )


@router.get("/runs/{run_id}/evidence", response_model=list[EvidenceRead])
async def list_evidence(run_id: UUID, session: DbSession) -> list[EvidenceItem]:
    if await session.get(ResearchRun, run_id) is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    return list(
        await session.scalars(
            select(EvidenceItem)
            .where(EvidenceItem.run_id == run_id)
            .order_by(EvidenceItem.relevance_score.desc())
        )
    )


@router.get("/runs/{run_id}/usage", response_model=UsageSummary)
async def get_usage(run_id: UUID, session: DbSession) -> UsageSummary:
    if await session.get(ResearchRun, run_id) is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    tool_calls = await session.scalar(
        select(func.count()).select_from(ToolExecution).where(ToolExecution.run_id == run_id)
    )
    llm_row = (
        await session.execute(
            select(
                func.count(LLMCall.id),
                func.coalesce(func.sum(LLMCall.input_tokens), 0),
                func.coalesce(func.sum(LLMCall.output_tokens), 0),
                func.coalesce(func.sum(LLMCall.estimated_cost_usd), 0),
            ).where(LLMCall.run_id == run_id)
        )
    ).one()
    tool_cost = await session.scalar(
        select(func.coalesce(func.sum(ToolExecution.estimated_cost_usd), 0)).where(
            ToolExecution.run_id == run_id
        )
    )
    return UsageSummary(
        tool_calls=tool_calls or 0,
        llm_calls=llm_row[0],
        input_tokens=llm_row[1],
        output_tokens=llm_row[2],
        estimated_cost_usd=Decimal(str(tool_cost)) + Decimal(str(llm_row[3])),
    )


async def _require_run(run_id: UUID, session: DbSession) -> None:
    if await session.get(ResearchRun, run_id) is None:
        raise HTTPException(status_code=404, detail="Research run not found")


@router.get("/runs/{run_id}/coverage", response_model=list[CoverageRead])
async def list_coverage(run_id: UUID, session: DbSession) -> list[CoverageAssessment]:
    await _require_run(run_id, session)
    return list(
        await session.scalars(
            select(CoverageAssessment)
            .where(CoverageAssessment.run_id == run_id)
            .order_by(CoverageAssessment.iteration, CoverageAssessment.question_id)
        )
    )


@router.get("/runs/{run_id}/gaps", response_model=list[ResearchGapRead])
async def list_gaps(run_id: UUID, session: DbSession) -> list[ResearchGap]:
    await _require_run(run_id, session)
    return list(
        await session.scalars(
            select(ResearchGap)
            .where(ResearchGap.run_id == run_id)
            .order_by(ResearchGap.iteration, ResearchGap.question_id)
        )
    )


@router.get("/runs/{run_id}/contradictions", response_model=list[ContradictionRead])
async def list_contradictions(run_id: UUID, session: DbSession) -> list[Contradiction]:
    await _require_run(run_id, session)
    return list(
        await session.scalars(
            select(Contradiction)
            .where(Contradiction.run_id == run_id)
            .order_by(Contradiction.iteration)
        )
    )


@router.get("/runs/{run_id}/critic", response_model=list[CriticReviewRead])
async def list_critic_reviews(run_id: UUID, session: DbSession) -> list[CriticReview]:
    await _require_run(run_id, session)
    return list(
        await session.scalars(
            select(CriticReview)
            .where(CriticReview.run_id == run_id)
            .order_by(CriticReview.iteration)
        )
    )


@router.get("/runs/{run_id}/report", response_model=ResearchReportRead)
async def get_report(run_id: UUID, session: DbSession) -> ResearchReport:
    await _require_run(run_id, session)
    report = await session.scalar(select(ResearchReport).where(ResearchReport.run_id == run_id))
    if report is None:
        raise HTTPException(status_code=404, detail="Report has not been generated")
    return report


@router.get("/runs/{run_id}/report/citations", response_model=list[ReportCitationRead])
async def list_report_citations(run_id: UUID, session: DbSession) -> list[ReportCitation]:
    report = await session.scalar(select(ResearchReport).where(ResearchReport.run_id == run_id))
    if report is None:
        raise HTTPException(status_code=404, detail="Report has not been generated")
    return list(
        await session.scalars(
            select(ReportCitation)
            .where(ReportCitation.report_id == report.id)
            .order_by(ReportCitation.marker)
        )
    )


@router.get(
    "/runs/{run_id}/report/validations", response_model=list[CitationValidationRead]
)
async def list_report_validations(
    run_id: UUID, session: DbSession
) -> list[CitationValidation]:
    report = await session.scalar(select(ResearchReport).where(ResearchReport.run_id == run_id))
    if report is None:
        raise HTTPException(status_code=404, detail="Report has not been generated")
    return list(
        await session.scalars(
            select(CitationValidation)
            .where(CitationValidation.report_id == report.id)
            .order_by(CitationValidation.attempt)
        )
    )
