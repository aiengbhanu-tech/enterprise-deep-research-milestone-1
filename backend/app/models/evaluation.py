from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class ResearchEvaluation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "research_evaluations"
    __table_args__ = (UniqueConstraint("run_id", name="uq_research_evaluations_run_id"),)

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    evaluator_version: Mapped[str] = mapped_column(String(32), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    citation_validity_score: Mapped[float] = mapped_column(Float, nullable=False)
    citation_coverage_score: Mapped[float] = mapped_column(Float, nullable=False)
    source_quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    source_diversity_score: Mapped[float] = mapped_column(Float, nullable=False)
    research_coverage_score: Mapped[float] = mapped_column(Float, nullable=False)
    cost_efficiency_score: Mapped[float] = mapped_column(Float, nullable=False)
    latency_score: Mapped[float] = mapped_column(Float, nullable=False)
    total_sources: Mapped[int] = mapped_column(Integer, nullable=False)
    total_evidence: Mapped[int] = mapped_column(Integer, nullable=False)
    total_citations: Mapped[int] = mapped_column(Integer, nullable=False)
    unsupported_claims: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    total_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_reasons: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
