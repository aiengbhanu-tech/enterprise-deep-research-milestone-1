import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.evidence import LLMCall
from app.models.report import CitationValidation, ReportCitation, ResearchReport
from app.providers.llm import LLMResponse, get_llm_provider
from app.services.citation_validator import CitationCheck

settings = get_settings()


def _unique_evidence(evidence: list[dict]) -> list[dict]:
    return list({str(item["id"]): item for item in evidence}.values())


def _mock_report(query: str, evidence: list[dict], limitations: list[str]) -> dict:
    groups: dict[str, list[dict]] = {}
    for item in _unique_evidence(evidence):
        groups.setdefault(str(item.get("question", "Research findings")), []).append(item)
    sections = []
    for index, (question, items) in enumerate(groups.items(), 1):
        excerpt = " ".join(str(item.get("content", ""))[:500] for item in items[:2])
        sections.append(
            {
                "key": f"finding-{index}",
                "heading": question,
                "body": excerpt or "No reliable evidence was retrieved for this question.",
                "citations": [str(item["id"]) for item in items[:2]],
            }
        )
    return {
        "title": f"Investment research: {query}",
        "executive_summary": "The evidence below summarizes market structure, company strategy, recent developments, catalysts, and material risks.",
        "recommendation": "watch",
        "confidence": 0.65 if evidence else 0.1,
        "sections": sections,
        "limitations": limitations,
    }


def _parse_json(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0]
    parsed = json.loads(content)
    required = {"title", "executive_summary", "recommendation", "confidence", "sections"}
    if not required.issubset(parsed):
        raise ValueError(f"LLM report is missing fields: {sorted(required - set(parsed))}")
    return parsed


async def _record_llm(run_id: str, purpose: str, response: LLMResponse, started: float) -> None:
    cost = Decimal(str(
        response.input_tokens * settings.llm_input_cost_per_million / 1_000_000
        + response.output_tokens * settings.llm_output_cost_per_million / 1_000_000
    ))
    async with SessionLocal() as session:
        session.add(
            LLMCall(
                run_id=UUID(run_id), purpose=purpose, provider=response.provider,
                model=response.model, input_tokens=response.input_tokens,
                output_tokens=response.output_tokens, cached_tokens=response.cached_tokens,
                latency_ms=int((time.perf_counter() - started) * 1000),
                estimated_cost_usd=cost, trace_id=response.trace_id,
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()


async def synthesize_report(
    run_id: str, query: str, evidence: list[dict], critic: dict, contradictions: list[dict]
) -> dict:
    evidence = _unique_evidence(evidence)
    limitations = list(critic.get("missing_questions", []))
    if settings.llm_provider == "mock":
        return _mock_report(query, evidence, limitations)

    context = [
        {
            "id": str(item["id"]), "question": item.get("question"),
            "source": item.get("source"), "source_quality": item.get("source_quality"),
            "passage": str(item.get("content", ""))[:2500],
        }
        for item in evidence[:60]
    ]
    prompt = {
        "query": query,
        "evidence": context,
        "critic": critic,
        "contradictions": contradictions,
        "instructions": (
            "Return JSON only. Write an investment-style report grounded solely in evidence. "
            "Required keys: title, executive_summary, recommendation (buy/hold/sell/watch), "
            "confidence (0..1), limitations, sections. Each section requires key, heading, body, "
            "and citations containing exact evidence IDs. Mention unresolved contradictions."
        ),
    }
    started = time.perf_counter()
    response = await get_llm_provider().generate(
        [
            {"role": "system", "content": "You are a rigorous investment research analyst."},
            {"role": "user", "content": json.dumps(prompt)},
        ],
        model=settings.openai_model,
    )
    await _record_llm(run_id, "report_synthesis", response, started)
    return _parse_json(response.content)


def render_markdown(report: dict, citations: list[dict]) -> str:
    marker_by_pair = {
        (item["section_key"], str(item["evidence_id"])): item["marker"] for item in citations
    }
    lines = [f"# {report['title']}", "", report["executive_summary"], ""]
    for section in report.get("sections", []):
        lines.extend([f"## {section['heading']}", "", section["body"]])
        markers = [
            marker_by_pair.get((section["key"], str(evidence_id)))
            for evidence_id in section.get("citations", [])
        ]
        markers = [item for item in markers if item]
        if markers:
            lines.extend(["", " ".join(f"[{marker}]" for marker in markers)])
        lines.append("")
    lines.extend(["## Investment view", "", f"**Recommendation:** {report['recommendation']}", "", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report.get("limitations", []))
    return "\n".join(lines)


async def persist_report(
    run_id: str, report: dict, validation: CitationCheck, attempts: int
) -> dict:
    async with SessionLocal() as session:
        existing = await session.scalar(select(ResearchReport).where(ResearchReport.run_id == UUID(run_id)))
        if existing:
            await session.delete(existing)
            await session.flush()
        row = ResearchReport(
            run_id=UUID(run_id), title=report["title"],
            executive_summary=report["executive_summary"], recommendation=report["recommendation"],
            confidence=float(report["confidence"]), sections=report.get("sections", []),
            limitations=report.get("limitations", []), markdown="pending",
            validation_status="valid" if validation.valid else "invalid",
            validation_score=validation.score, repair_attempts=attempts,
        )
        session.add(row)
        await session.flush()
        normalized = []
        for index, item in enumerate(validation.citations, 1):
            citation = {**item, "marker": f"E{index}"}
            normalized.append(citation)
            session.add(
                ReportCitation(
                    report_id=row.id,
                    evidence_id=UUID(str(citation["evidence_id"])),
                    source_id=UUID(str(citation["source_id"])),
                    marker=citation["marker"],
                    section_key=citation["section_key"],
                    claim_text=citation["claim_text"],
                    support_score=citation["support_score"],
                    status=citation["status"],
                )
            )
        row.markdown = render_markdown(report, normalized)
        session.add(CitationValidation(
            report_id=row.id, attempt=attempts, valid=validation.valid,
            score=validation.score, issues=validation.issues,
        ))
        await session.commit()
        return {
            **report, "id": str(row.id), "markdown": row.markdown,
            "validation_status": row.validation_status,
            "validation_score": row.validation_score,
            "repair_attempts": attempts,
        }
