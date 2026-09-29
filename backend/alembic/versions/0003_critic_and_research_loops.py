"""Add coverage, gaps, contradictions, and critic reviews."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_critic_and_research_loops"
down_revision: str | None = "0002_evidence_and_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    ]


def run_fk() -> sa.Column:
    return sa.Column(
        "run_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey(
            "research_runs.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )


def upgrade() -> None:
    # A run can now contain multiple approval checkpoints.
    op.drop_constraint(
        "uq_approval_request_run",
        "approval_requests",
        type_="unique",
    )

    op.create_table(
        "coverage_assessments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        run_fk(),
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.String(100), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("independent_sources", sa.Integer(), nullable=False),
        sa.Column("average_quality", sa.Float(), nullable=False),
        sa.Column("has_primary_source", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        *timestamps(),
        sa.UniqueConstraint(
            "run_id",
            "iteration",
            "question_id",
            name="uq_coverage_run_iteration_question",
        ),
    )

    op.create_index(
        "ix_coverage_assessments_run_id",
        "coverage_assessments",
        ["run_id"],
    )

    op.create_table(
        "research_gaps",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        run_fk(),
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "follow_up_queries",
            postgresql.JSONB(),
            server_default="[]",
        ),
        sa.Column(
            "status",
            sa.String(32),
            server_default="open",
        ),
        *timestamps(),
    )

    op.create_index(
        "ix_research_gaps_run_id",
        "research_gaps",
        ["run_id"],
    )

    op.create_table(
        "contradictions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        run_fk(),
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("claim_a", sa.Text(), nullable=False),
        sa.Column("claim_b", sa.Text(), nullable=False),
        sa.Column(
            "evidence_a_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "evidence_items.id",
                ondelete="SET NULL",
            ),
        ),
        sa.Column(
            "evidence_b_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "evidence_items.id",
                ondelete="SET NULL",
            ),
        ),
        sa.Column("possible_reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            server_default="unresolved",
        ),
        *timestamps(),
    )

    op.create_index(
        "ix_contradictions_run_id",
        "contradictions",
        ["run_id"],
    )

    op.create_table(
        "critic_reviews",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        run_fk(),
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("coverage_score", sa.Float(), nullable=False),
        sa.Column(
            "missing_questions",
            postgresql.JSONB(),
            server_default="[]",
        ),
        sa.Column(
            "weak_claims",
            postgresql.JSONB(),
            server_default="[]",
        ),
        sa.Column(
            "follow_up_queries",
            postgresql.JSONB(),
            server_default="[]",
        ),
        sa.Column("rationale", sa.Text(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint(
            "run_id",
            "iteration",
            name="uq_critic_run_iteration",
        ),
    )

    op.create_index(
        "ix_critic_reviews_run_id",
        "critic_reviews",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_table("critic_reviews")
    op.drop_table("contradictions")
    op.drop_table("research_gaps")
    op.drop_table("coverage_assessments")

    op.create_unique_constraint(
        "uq_approval_request_run",
        "approval_requests",
        ["run_id"],
    )