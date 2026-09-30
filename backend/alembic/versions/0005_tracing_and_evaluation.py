"""Add persistent execution tracing and research evaluation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_tracing_and_evaluation"
down_revision: str | None = "0004_reports_and_citations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table(
        "execution_traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("parent_span_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("execution_traces.id", ondelete="SET NULL")),
        sa.Column("node_name", sa.String(100), nullable=False),
        sa.Column("span_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("input_summary", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("output_summary", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error_type", sa.String(255)),
        sa.Column("error_message", sa.Text()),
        sa.Column("span_attributes", postgresql.JSONB(), nullable=False, server_default="{}"),
        *timestamps(),
    )
    for column in ("run_id", "trace_id", "parent_span_id", "node_name", "status"):
        op.create_index(f"ix_execution_traces_{column}", "execution_traces", [column])

    op.create_table(
        "research_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evaluator_version", sa.String(32), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("citation_validity_score", sa.Float(), nullable=False),
        sa.Column("citation_coverage_score", sa.Float(), nullable=False),
        sa.Column("source_quality_score", sa.Float(), nullable=False),
        sa.Column("source_diversity_score", sa.Float(), nullable=False),
        sa.Column("research_coverage_score", sa.Float(), nullable=False),
        sa.Column("cost_efficiency_score", sa.Float(), nullable=False),
        sa.Column("latency_score", sa.Float(), nullable=False),
        sa.Column("total_sources", sa.Integer(), nullable=False),
        sa.Column("total_evidence", sa.Integer(), nullable=False),
        sa.Column("total_citations", sa.Integer(), nullable=False),
        sa.Column("unsupported_claims", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("total_latency_ms", sa.Integer(), nullable=False),
        sa.Column("failure_reasons", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("metrics", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("notes", sa.Text()),
        *timestamps(),
        sa.UniqueConstraint("run_id", name="uq_research_evaluations_run_id"),
    )
    op.create_index("ix_research_evaluations_run_id", "research_evaluations", ["run_id"])


def downgrade() -> None:
    op.drop_table("research_evaluations")
    op.drop_table("execution_traces")
