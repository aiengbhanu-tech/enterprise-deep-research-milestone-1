"""Add run deadlines, cancellation metadata, and Celery task identifiers."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_run_deadlines"
down_revision: str | None = "0005_tracing_and_evaluation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_runs",
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "research_runs",
        sa.Column(
            "cancellation_requested_at",
            sa.DateTime(timezone=True),
        ),
    )
    op.add_column(
        "research_runs",
        sa.Column("cancellation_reason", sa.Text()),
    )
    op.add_column(
        "research_runs",
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "research_runs",
        sa.Column("celery_task_id", sa.String(64)),
    )
    op.add_column(
        "research_runs",
        sa.Column("deadline_task_id", sa.String(64)),
    )

    # Backfill existing runs before making deadline_at non-nullable.
    op.execute(
        "UPDATE research_runs "
        "SET deadline_at = created_at + interval '15 minutes'"
    )

    op.alter_column(
        "research_runs",
        "deadline_at",
        nullable=False,
    )

    op.create_index(
        "ix_research_runs_deadline_at",
        "research_runs",
        ["deadline_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_runs_deadline_at",
        table_name="research_runs",
    )

    for column in (
        "deadline_task_id",
        "celery_task_id",
        "finished_at",
        "cancellation_reason",
        "cancellation_requested_at",
        "deadline_at",
    ):
        op.drop_column("research_runs", column)