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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class ResearchReport(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "research_reports"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            name="uq_research_reports_run_id",
        ),
    )

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "research_runs.id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    executive_summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    recommendation: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    sections: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    limitations: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    markdown: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    validation_status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        nullable=False,
    )

    validation_score: Mapped[float] = mapped_column(
        Float,
        default=0,
        nullable=False,
    )

    repair_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    citations: Mapped[list["ReportCitation"]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
    )


class ReportCitation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "report_citations"
    __table_args__ = (
        UniqueConstraint(
            "report_id",
            "marker",
            name="uq_report_citations_report_marker",
        ),
    )

    report_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "research_reports.id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )

    evidence_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "evidence_items.id",
            ondelete="RESTRICT",
        ),
        index=True,
        nullable=False,
    )

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "sources.id",
            ondelete="RESTRICT",
        ),
        index=True,
        nullable=False,
    )

    marker: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    section_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    claim_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    support_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    report: Mapped["ResearchReport"] = relationship(
        back_populates="citations",
    )


class CitationValidation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "citation_validations"

    report_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "research_reports.id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )

    attempt: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    valid: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    issues: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )