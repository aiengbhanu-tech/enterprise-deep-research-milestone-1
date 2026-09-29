import re
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.review import (
    Contradiction,
    CoverageAssessment,
    CriticReview,
    ResearchGap,
)

settings = get_settings()

PERCENT_PATTERN = re.compile(
    r"\b(\d{1,3}(?:\.\d+)?)\s*%"
)


@dataclass(frozen=True)
class ReviewResult:
    coverage: list[dict]
    contradictions: list[dict]
    gaps: list[dict]
    critic: dict


def _source_identity(url: str) -> str:
    hostname = urlsplit(url).hostname or url
    return hostname.removeprefix("www.")


def analyze_coverage(
    plan: list[dict],
    evidence: list[dict],
) -> list[dict]:
    rows: list[dict] = []

    for item in plan:
        matches = [
            entry
            for entry in evidence
            if entry.get("question") == item["question"]
        ]

        sources = {
            _source_identity(entry.get("source", ""))
            for entry in matches
        }

        qualities = [
            float(entry.get("source_quality", 0.5))
            for entry in matches
        ]

        average_quality = (
            sum(qualities) / len(qualities)
            if qualities
            else 0.0
        )

        has_primary_source = any(
            score >= 0.85
            for score in qualities
        )

        evidence_factor = min(
            len(matches) / 4,
            1.0,
        )

        diversity_factor = min(
            len(sources) / 2,
            1.0,
        )

        score = round(
            (0.40 * evidence_factor)
            + (0.35 * diversity_factor)
            + (0.25 * average_quality),
            4,
        )

        status = (
            "sufficient"
            if (
                score
                >= settings.research_min_coverage_score
                and average_quality
                >= settings.research_min_source_quality
            )
            else "weak"
        )

        if not matches:
            status = "missing"

        rows.append(
            {
                "question_id": item["id"],
                "question": item["question"],
                "evidence_count": len(matches),
                "independent_sources": len(sources),
                "average_quality": round(
                    average_quality,
                    4,
                ),
                "has_primary_source": has_primary_source,
                "score": score,
                "status": status,
            }
        )

    return rows


def detect_contradictions(
    evidence: list[dict],
) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)

    for item in evidence:
        question = item.get(
            "question",
            "unknown",
        )
        grouped[question].append(item)

    contradictions: list[dict] = []

    for topic, items in grouped.items():
        claims: list[tuple[str, dict]] = []

        for item in items:
            match = PERCENT_PATTERN.search(
                item.get("content", "")
            )

            if match:
                claims.append(
                    (match.group(1), item)
                )

        for index, (value_a, item_a) in enumerate(claims):
            for value_b, item_b in claims[index + 1 :]:
                same_value = value_a == value_b
                same_source = (
                    item_a.get("source")
                    == item_b.get("source")
                )

                if same_value or same_source:
                    continue

                contradictions.append(
                    {
                        "topic": topic,
                        "claim_a": (
                            f"{value_a}% reported by "
                            f"{item_a.get('source')}"
                        ),
                        "claim_b": (
                            f"{value_b}% reported by "
                            f"{item_b.get('source')}"
                        ),
                        "evidence_a_id": item_a.get("id"),
                        "evidence_b_id": item_b.get("id"),
                        "possible_reason": (
                            "Figures may use different periods, "
                            "categories, or market definitions."
                        ),
                        "status": "unresolved",
                    }
                )
                break

            if (
                contradictions
                and contradictions[-1]["topic"] == topic
            ):
                break

    return contradictions


def build_review(
    plan: list[dict],
    evidence: list[dict],
    iteration: int,
    max_iterations: int,
) -> ReviewResult:
    coverage = analyze_coverage(
        plan,
        evidence,
    )

    contradictions = detect_contradictions(
        evidence,
    )

    weak = [
        item
        for item in coverage
        if item["status"] != "sufficient"
    ]

    gaps = [
        {
            "question_id": item["question_id"],
            "question": item["question"],
            "description": (
                f"Insufficient evidence for: "
                f"{item['question']}"
            ),
            "follow_up_queries": [
                (
                    f"{item['question']} "
                    "official data recent"
                ),
                (
                    f"{item['question']} "
                    "independent analysis recent"
                ),
            ],
            "status": "open",
        }
        for item in weak
    ]

    gaps.extend(
        {
            "question_id": f"contradiction-{index}",
            "question": item["topic"],
            "description": (
                "Resolve contradictory evidence for: "
                f"{item['topic']}"
            ),
            "follow_up_queries": [
                (
                    f"{item['topic']} "
                    "official definition methodology"
                ),
                (
                    f"{item['topic']} "
                    "latest primary source data"
                ),
            ],
            "status": "open",
        }
        for index, item in enumerate(contradictions)
    )

    coverage_score = round(
        sum(item["score"] for item in coverage)
        / len(coverage),
        4,
    )

    enough = not weak and not contradictions
    exhausted = iteration >= max_iterations

    if enough:
        decision = "complete"
    elif exhausted:
        decision = "complete_with_limitations"
    else:
        decision = "continue"

    follow_up_queries = [
        query
        for gap in gaps
        for query in gap["follow_up_queries"]
    ]

    critic = {
        "decision": decision,
        "coverage_score": coverage_score,
        "missing_questions": [
            item["question"]
            for item in weak
        ],
        "weak_claims": [
            item["topic"]
            for item in contradictions
        ],
        "follow_up_queries": follow_up_queries[:10],
        "rationale": (
            "All planned questions have sufficient "
            "independent support."
            if enough
            else (
                "Iteration limit reached; unresolved "
                "limitations must be disclosed."
                if exhausted
                else (
                    "Coverage or contradictions require "
                    "another bounded research pass."
                )
            )
        ),
    }

    return ReviewResult(
        coverage=coverage,
        contradictions=contradictions,
        gaps=gaps,
        critic=critic,
    )


async def persist_review(
    run_id: str,
    iteration: int,
    result: ReviewResult,
) -> None:
    run_uuid = UUID(run_id)

    async with SessionLocal() as session:
        session.add_all(
            [
                CoverageAssessment(
                    run_id=run_uuid,
                    iteration=iteration,
                    **item,
                )
                for item in result.coverage
            ]
        )

        session.add_all(
            [
                ResearchGap(
                    run_id=run_uuid,
                    iteration=iteration,
                    question_id=item["question_id"],
                    description=item["description"],
                    follow_up_queries=(
                        item["follow_up_queries"]
                    ),
                    status=item["status"],
                )
                for item in result.gaps
            ]
        )

        session.add_all(
            [
                Contradiction(
                    run_id=run_uuid,
                    iteration=iteration,
                    topic=item["topic"],
                    claim_a=item["claim_a"],
                    claim_b=item["claim_b"],
                    evidence_a_id=UUID(
                        item["evidence_a_id"]
                    ),
                    evidence_b_id=UUID(
                        item["evidence_b_id"]
                    ),
                    possible_reason=(
                        item["possible_reason"]
                    ),
                    status=item["status"],
                )
                for item in result.contradictions
                if (
                    item.get("evidence_a_id")
                    and item.get("evidence_b_id")
                )
            ]
        )

        session.add(
            CriticReview(
                run_id=run_uuid,
                iteration=iteration,
                **result.critic,
            )
        )

        await session.commit()