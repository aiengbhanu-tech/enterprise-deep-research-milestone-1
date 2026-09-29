import re
from dataclasses import dataclass
from app.core.config import get_settings

WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class CitationCheck:
    valid: bool
    score: float
    issues: list[dict]
    citations: list[dict]


def _terms(text: str) -> set[str]:
    stop = {"about", "after", "also", "and", "are", "for", "from", "into", "that", "the", "their", "this", "was", "were", "with"}
    return {word for word in WORD_RE.findall(text.lower()) if len(word) > 2 and word not in stop}


def support_score(claim: str, passage: str) -> float:
    claim_terms = _terms(claim)
    if not claim_terms:
        return 0
    return round(len(claim_terms & _terms(passage)) / len(claim_terms), 4)


def validate_report(report: dict, evidence: list[dict]) -> CitationCheck:
    settings = get_settings()
    evidence_by_id = {str(item["id"]): item for item in evidence}
    issues: list[dict] = []
    citations: list[dict] = []

    for section_index, section in enumerate(report.get("sections", [])):
        key = str(section.get("key") or f"section-{section_index + 1}")
        body = str(section.get("body", "")).strip()
        cited_ids = list(dict.fromkeys(str(item) for item in section.get("citations", [])))
        if len(body) >= 80 and not cited_ids:
            issues.append({"type": "uncited_section", "section": key})
        for evidence_id in cited_ids:
            item = evidence_by_id.get(evidence_id)
            if item is None:
                issues.append(
                    {"type": "unknown_evidence", "section": key, "evidence_id": evidence_id}
                )
                continue
            score = support_score(body, str(item.get("content", "")))
            status = "supported" if score >= settings.citation_min_support_score else "weak"
            citations.append(
                {
                    "evidence_id": evidence_id,
                    "source_id": item.get("source_id"),
                    "section_key": key,
                    "claim_text": body,
                    "support_score": score,
                    "status": status,
                }
            )
            if status == "weak":
                issues.append(
                    {
                        "type": "weak_support",
                        "section": key,
                        "evidence_id": evidence_id,
                        "support_score": score,
                    }
                )

    score = round(
        sum(item["support_score"] for item in citations) / len(citations), 4
    ) if citations else 0
    return CitationCheck(valid=not issues and bool(citations), score=score, issues=issues, citations=citations)


def repair_report_citations(report: dict, evidence: list[dict]) -> dict:
    """Deterministic safety repair: attach the best lexical evidence to invalid sections."""
    repaired = {**report, "sections": [dict(section) for section in report.get("sections", [])]}
    valid_ids = {str(item["id"]) for item in evidence}
    for section in repaired["sections"]:
        body = str(section.get("body", ""))
        cited = [str(item) for item in section.get("citations", []) if str(item) in valid_ids]
        ranked = sorted(
            evidence,
            key=lambda item: support_score(body, str(item.get("content", ""))),
            reverse=True,
        )
        if not cited or max(
            (support_score(body, str(next(item for item in evidence if str(item["id"]) == eid).get("content", ""))) for eid in cited),
            default=0,
        ) < get_settings().citation_min_support_score:
            cited = [str(item["id"]) for item in ranked[:2] if support_score(body, str(item.get("content", ""))) > 0]
        section["citations"] = cited
    return repaired
