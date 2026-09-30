from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class ExecutionTrace(UUIDMixin, TimestampMixin, Base):
    """
    Stores one execution span for an agent node or external tool.

    A research run will have several traces:

    planner
        └── search
            ├── Tavily search
            ├── web fetch
            └── evidence extraction
        └── critic
        └── synthesis
        └── citation validation
    """

    __tablename__ = "execution_traces"

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "research_runs.id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )

    trace_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )

    parent_span_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "execution_traces.id",
            ondelete="SET NULL",
        ),
        index=True,
        nullable=True,
    )

    node_name: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )

    span_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        index=True,
        nullable=False,
    )

    attempt: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    input_summary: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    output_summary: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    error_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    span_attributes: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    parent: Mapped["ExecutionTrace | None"] = relationship(
        remote_side="ExecutionTrace.id",
        back_populates="children",
    )

    children: Mapped[list["ExecutionTrace"]] = relationship(
        back_populates="parent",
    )