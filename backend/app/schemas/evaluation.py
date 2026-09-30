from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ExecutionTraceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trace_id: str
    parent_span_id: UUID | None
    node_name: str
    span_type: str
    status: str
    attempt: int
    started_at: datetime
    ended_at: datetime | None
    latency_ms: int | None
    input_summary: dict
    output_summary: dict
    error_type: str | None
    error_message: str | None
    span_attributes: dict


class ResearchEvaluationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    evaluator_version: str
    passed: bool
    overall_score: float
    citation_validity_score: float
    citation_coverage_score: float
    source_quality_score: float
    source_diversity_score: float
    research_coverage_score: float
    cost_efficiency_score: float
    latency_score: float
    total_sources: int
    total_evidence: int
    total_citations: int
    unsupported_claims: int
    estimated_cost_usd: Decimal
    total_latency_ms: int
    failure_reasons: list
    metrics: dict
    notes: str | None
    created_at: datetime
    updated_at: datetime
