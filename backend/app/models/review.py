from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class CoverageAssessment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "coverage_assessments"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "iteration",
            "question_id",
            name="uq_coverage_run_iteration_question",
        ),
    )

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        index=True,
    )
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)
    question_id: Mapped[str] = mapped_column(String(100), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    independent_sources: Mapped[int] = mapped_column(Integer, nullable=False)
    average_quality: Mapped[float] = mapped_column(Float, nullable=False)
    has_primary_source: Mapped[bool] = mapped_column(Boolean, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class ResearchGap(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "research_gaps"

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        index=True,
    )
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)
    question_id: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    follow_up_queries: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(32), default="open")


class Contradiction(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "contradictions"

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        index=True,
    )
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    claim_a: Mapped[str] = mapped_column(Text, nullable=False)
    claim_b: Mapped[str] = mapped_column(Text, nullable=False)

    evidence_a_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("evidence_items.id", ondelete="SET NULL")
    )
    evidence_b_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("evidence_items.id", ondelete="SET NULL")
    )

    possible_reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="unresolved",
    )


class CriticReview(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "critic_reviews"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "iteration",
            name="uq_critic_run_iteration",
        ),
    )

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        index=True,
    )
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    coverage_score: Mapped[float] = mapped_column(Float, nullable=False)
    missing_questions: Mapped[list] = mapped_column(JSONB, default=list)
    weak_claims: Mapped[list] = mapped_column(JSONB, default=list)
    follow_up_queries: Mapped[list] = mapped_column(JSONB, default=list)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)