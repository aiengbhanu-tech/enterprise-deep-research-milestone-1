import operator
from typing import Annotated, TypedDict


class ResearchState(TypedDict, total=False):
    run_id: str
    query: str
    budget_usd: float
    plan: list[dict[str, str]]
    approval: dict[str, str]
    evidence: Annotated[list[dict[str, str]], operator.add]
    report: dict[str, object]
    report_draft: dict[str, object]
    citation_validation: dict[str, object]
    repair_attempts: int
    iteration: int
    active_questions: list[dict[str, str]]
    coverage: list[dict]
    contradictions: list[dict]
    gaps: list[dict]
    critic: dict
    additional_approval: dict[str, str]
    status: str
