from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.evaluation import ResearchEvaluation
from app.models.evidence import EvidenceItem, LLMCall, Source, ToolExecution
from app.models.report import ReportCitation, ResearchReport
from app.models.research import ResearchRun
from app.models.review import CriticReview
from app.models.trace import ExecutionTrace

EVALUATOR_VERSION = "v1"


@dataclass(frozen=True)
class EvaluationScores:
    overall: float
    passed: bool
    failure_reasons: list[str]


def calculate_overall_score(metrics: dict[str, float]) -> EvaluationScores:
    weights = {
        "citation_validity": 0.20,
        "citation_coverage": 0.15,
        "source_quality": 0.15,
        "source_diversity": 0.10,
        "research_coverage": 0.20,
        "cost_efficiency": 0.10,
        "latency": 0.10,
    }
    overall = round(sum(metrics[name] * weight for name, weight in weights.items()), 4)
    failures = []
    if metrics["citation_validity"] < 0.8:
        failures.append("Citation validity is below 0.80")
    if metrics["citation_coverage"] < 0.8:
        failures.append("Citation coverage is below 0.80")
    if metrics["research_coverage"] < 0.7:
        failures.append("Research coverage is below 0.70")
    if overall < 0.7:
        failures.append("Overall quality score is below 0.70")
    return EvaluationScores(overall=overall, passed=not failures, failure_reasons=failures)


async def evaluate_and_persist(run_id: str) -> dict:
    run_uuid = UUID(run_id)
    async with SessionLocal() as session:
        run = await session.get(ResearchRun, run_uuid)
        report = await session.scalar(
            select(ResearchReport).where(ResearchReport.run_id == run_uuid)
        )
        sources = list(await session.scalars(select(Source).where(Source.run_id == run_uuid)))
        evidence_count = await session.scalar(
            select(func.count()).select_from(EvidenceItem).where(EvidenceItem.run_id == run_uuid)
        )
        citations = [] if report is None else list(
            await session.scalars(
                select(ReportCitation).where(ReportCitation.report_id == report.id)
            )
        )
        critic = await session.scalar(
            select(CriticReview)
            .where(CriticReview.run_id == run_uuid)
            .order_by(CriticReview.iteration.desc())
        )
        tool_cost = await session.scalar(
            select(func.coalesce(func.sum(ToolExecution.estimated_cost_usd), 0)).where(
                ToolExecution.run_id == run_uuid
            )
        )
        llm_cost = await session.scalar(
            select(func.coalesce(func.sum(LLMCall.estimated_cost_usd), 0)).where(
                LLMCall.run_id == run_uuid
            )
        )
        total_latency = await session.scalar(
            select(func.coalesce(func.sum(ExecutionTrace.latency_ms), 0)).where(
                ExecutionTrace.run_id == run_uuid
            )
        )

        supported = sum(item.status == "supported" for item in citations)
        citation_validity = supported / len(citations) if citations else 0
        sections = report.sections if report else []
        cited_sections = sum(bool(section.get("citations")) for section in sections)
        citation_coverage = cited_sections / len(sections) if sections else 0
        source_quality = (
            sum(item.quality_score for item in sources) / len(sources) if sources else 0
        )
        hosts = {urlsplit(item.url).hostname for item in sources if urlsplit(item.url).hostname}
        source_diversity = min(len(hosts) / 5, 1.0)
        research_coverage = critic.coverage_score if critic else 0
        total_cost = Decimal(str(tool_cost)) + Decimal(str(llm_cost))
        budget = Decimal(str(run.budget_usd)) if run else Decimal("1")
        cost_efficiency = max(0.0, 1.0 - float(total_cost / budget)) if budget else 0
        latency_score = 1 / (1 + int(total_latency or 0) / 60_000)

        metrics = {
            "citation_validity": round(citation_validity, 4),
            "citation_coverage": round(citation_coverage, 4),
            "source_quality": round(source_quality, 4),
            "source_diversity": round(source_diversity, 4),
            "research_coverage": round(research_coverage, 4),
            "cost_efficiency": round(cost_efficiency, 4),
            "latency": round(latency_score, 4),
        }
        result = calculate_overall_score(metrics)
        values = {
            "evaluator_version": EVALUATOR_VERSION,
            "passed": result.passed,
            "overall_score": result.overall,
            "citation_validity_score": metrics["citation_validity"],
            "citation_coverage_score": metrics["citation_coverage"],
            "source_quality_score": metrics["source_quality"],
            "source_diversity_score": metrics["source_diversity"],
            "research_coverage_score": metrics["research_coverage"],
            "cost_efficiency_score": metrics["cost_efficiency"],
            "latency_score": metrics["latency"],
            "total_sources": len(sources),
            "total_evidence": int(evidence_count or 0),
            "total_citations": len(citations),
            "unsupported_claims": len(citations) - supported,
            "estimated_cost_usd": total_cost,
            "total_latency_ms": int(total_latency or 0),
            "failure_reasons": result.failure_reasons,
            "metrics": metrics,
        }
        existing = await session.scalar(
            select(ResearchEvaluation).where(ResearchEvaluation.run_id == run_uuid)
        )
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
            row = existing
        else:
            row = ResearchEvaluation(run_id=run_uuid, **values)
            session.add(row)
        await session.commit()
        return {**values, "estimated_cost_usd": str(total_cost)}
