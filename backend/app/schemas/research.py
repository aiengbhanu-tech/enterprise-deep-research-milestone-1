from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ResearchRunCreate(BaseModel):
    query: str = Field(min_length=10, max_length=5000)
    budget_usd: Decimal | None = Field(default=None, gt=0, le=100)


class ResearchRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    thread_id: str
    query: str
    status: str
    budget_usd: Decimal
    plan: dict | list | None
    result: dict | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=2000)


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    status: str
    reason: str
    decision_note: str | None
    created_at: datetime
    decided_at: datetime | None


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str
    title: str | None
    publisher: str | None
    retrieved_at: datetime
    content_type: str | None
    quality_score: float
    quality_details: dict


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    question: str
    passage: str
    locator: dict
    relevance_score: float


class UsageSummary(BaseModel):
    tool_calls: int
    llm_calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal
    
class CoverageRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    iteration: int
    question_id: str
    question: str
    evidence_count: int
    independent_sources: int
    average_quality: float
    has_primary_source: bool
    score: float
    status: str


class ResearchGapRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID
    iteration: int
    question_id: str
    description: str
    follow_up_queries: list
    status: str


class ContradictionRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID
    iteration: int
    topic: str
    claim_a: str
    claim_b: str
    possible_reason: str
    status: str


class CriticReviewRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    iteration: int
    decision: str
    coverage_score: float
    missing_questions: list
    weak_claims: list
    follow_up_queries: list
    rationale: str
