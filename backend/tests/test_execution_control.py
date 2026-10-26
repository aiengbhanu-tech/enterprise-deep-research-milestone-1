import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.services.execution_control as control_module
from app.models.research import RunStatus
from app.services.execution_control import (
    RunCancelled,
    RunTimedOut,
    bounded_timeout,
    ensure_run_active,
    run_controlled,
)

NOW = datetime(
    2026,
    10,
    26,
    12,
    0,
    tzinfo=UTC,
)


def test_cancelled_run_is_rejected_before_next_operation() -> None:
    with pytest.raises(RunCancelled):
        ensure_run_active(
            RunStatus.CANCELLED,
            NOW + timedelta(minutes=5),
            NOW,
        )


def test_expired_deadline_becomes_timed_out() -> None:
    with pytest.raises(RunTimedOut):
        ensure_run_active(
            RunStatus.RUNNING,
            NOW - timedelta(seconds=1),
            NOW,
        )


def test_operation_timeout_is_bounded_by_run_deadline() -> None:
    timeout = bounded_timeout(
        NOW + timedelta(seconds=7),
        requested_seconds=30,
        now=NOW,
    )

    assert timeout == 7


def test_operation_timeout_uses_smaller_provider_limit() -> None:
    timeout = bounded_timeout(
        NOW + timedelta(minutes=5),
        requested_seconds=20,
        now=NOW,
    )

    assert timeout == 20


async def test_running_operation_stops_when_cancellation_is_observed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def fake_check(_run_id):
        nonlocal calls

        calls += 1

        if calls > 1:
            raise RunCancelled(
                "cancelled during operation"
            )

        return SimpleNamespace(
            deadline_at=(
                NOW + timedelta(minutes=5)
            )
        )

    monkeypatch.setattr(
        control_module,
        "check_run_control",
        fake_check,
    )

    with pytest.raises(RunCancelled):
        await run_controlled(
            uuid4(),
            asyncio.sleep(10),
            timeout_seconds=30,
            poll_seconds=0.001,
        )