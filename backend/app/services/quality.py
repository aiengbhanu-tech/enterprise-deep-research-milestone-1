from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class QualityScore:
    score: float
    details: dict[str, float | str]


def score_source(url: str, text: str) -> QualityScore:
    host = (urlsplit(url).hostname or "").lower()
    authority = 0.55
    source_type = "general_web"
    if host.endswith(".gov.in") or host.endswith(".gov"):
        authority, source_type = 0.95, "government"
    elif any(token in host for token in ("sebi.gov", "rbi.org", "niti.gov")):
        authority, source_type = 0.95, "regulator"
    elif any(token in host for token in ("reuters.com", "bloomberg.com", "ft.com")):
        authority, source_type = 0.82, "established_news"
    elif any(token in host for token in ("investor", "annualreport", "bseindia", "nseindia")):
        authority, source_type = 0.88, "company_or_exchange_filing"

    completeness = min(len(text) / 5_000, 1.0)
    score = round((0.7 * authority) + (0.3 * completeness), 4)
    return QualityScore(
        score=score,
        details={
            "authority": authority,
            "completeness": round(completeness, 4),
            "source_type": source_type,
            "method": "deterministic-v1",
        },
    )
