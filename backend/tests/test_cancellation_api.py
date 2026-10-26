from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

import app.api.routes.research as research_routes
from app.models.research import ResearchRun, RunStatus
from app.schemas.research import CancellationRequest


def make_run(status: RunStatus) -> ResearchRun:
    return ResearchRun(
        id=uuid4(),
        thread_id=str(uuid4()),
        query=(
            "Analyze a market with "
            "authoritative evidence"
        ),
        status=status,
        budget_usd=Decimal("2.0"),
        deadline_at=(
            datetime.now(UTC)
            + timedelta(minutes=10)
        ),
        celery_task_id="execution-task",
        deadline_task_id="deadline-task",
    )


async def test_cancel_endpoint_persists_state_and_revokes_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = make_run(RunStatus.RUNNING)

    session = AsyncMock()
    session.get.return_value = run
    session.scalars.return_value = []

    publish = AsyncMock()
    revoke = MagicMock()

    monkeypatch.setattr(
        research_routes,
        "publish_event",
        publish,
    )
    monkeypatch.setattr(
        research_routes.celery_app.control,
        "revoke",
        revoke,
    )

    result = await research_routes.cancel_run(
        run.id,
        CancellationRequest(
            reason="No longer needed"
        ),
        session,
    )

    assert result.status == RunStatus.CANCELLED
    assert (
        result.cancellation_reason
        == "No longer needed"
    )
    assert result.finished_at is not None
    assert revoke.call_count == 2

    publish.assert_any_await(
        str(run.id),
        "run.cancellation_requested",
        {
            "run_id": str(run.id),
            "reason": "No longer needed",
        },
    )


async def test_completed_run_cannot_be_cancelled() -> None:
    run = make_run(RunStatus.COMPLETED)

    session = AsyncMock()
    session.get.return_value = run

    with pytest.raises(HTTPException) as exc_info:
        await research_routes.cancel_run(
            run.id,
            CancellationRequest(
                reason="Too late"
            ),
            session,
        )

    assert exc_info.value.status_code == 409