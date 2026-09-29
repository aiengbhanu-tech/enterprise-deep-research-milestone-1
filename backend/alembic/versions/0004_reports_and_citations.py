"""Add persistent reports, citations, and citation validation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_reports_and_citations"
down_revision: str | None = "0003_critic_and_research_loops"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table(
        "research_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("executive_summary", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("sections", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("limitations", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("validation_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("validation_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("repair_attempts", sa.Integer(), nullable=False, server_default="0"),
        *timestamps(),
        sa.UniqueConstraint("run_id", name="uq_research_reports_run_id"),
    )
    op.create_index("ix_research_reports_run_id", "research_reports", ["run_id"])

    op.create_table(
        "report_citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evidence_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evidence_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("marker", sa.String(32), nullable=False),
        sa.Column("section_key", sa.String(100), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("support_score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("report_id", "marker", name="uq_report_citations_report_marker"),
    )
    op.create_index("ix_report_citations_report_id", "report_citations", ["report_id"])
    op.create_index("ix_report_citations_evidence_id", "report_citations", ["evidence_id"])
    op.create_index("ix_report_citations_source_id", "report_citations", ["source_id"])

    op.create_table(
        "citation_validations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("research_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("issues", postgresql.JSONB(), nullable=False, server_default="[]"),
        *timestamps(),
    )
    op.create_index("ix_citation_validations_report_id", "citation_validations", ["report_id"])


def downgrade() -> None:
    op.drop_table("citation_validations")
    op.drop_table("report_citations")
    op.drop_table("research_reports")
