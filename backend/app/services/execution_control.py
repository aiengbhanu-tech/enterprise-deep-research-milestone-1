import asyncio
import inspect
from collections.abc import Awaitable
from contextlib import suppress
from datetime import UTC, datetime
from typing import TypeVar
from uuid import UUID

from app.db.session import SessionLocal
from app.models.research import ResearchRun, RunStatus

T = TypeVar("T")


class RunControlError(RuntimeError):
    terminal_status: RunStatus


class RunCancelled(RunControlError):
    terminal_status = RunStatus.CANCELLED


class RunTimedOut(RunControlError):
    terminal_status = RunStatus.TIMED_OUT


def ensure_run_active(
    status: str,
    deadline_at: datetime,
    now: datetime | None = None,
) -> None:
    current_time = now or datetime.now(UTC)

    if status == RunStatus.CANCELLED:
        raise RunCancelled("Research run was cancelled")

    if status == RunStatus.TIMED_OUT or deadline_at <= current_time:
        raise RunTimedOut("Research run deadline exceeded")


def bounded_timeout(
    deadline_at: datetime,
    requested_seconds: float,
    now: datetime | None = None,
) -> float:
    remaining = (deadline_at - (now or datetime.now(UTC))).total_seconds()

    if remaining <= 0:
        raise RunTimedOut("Research run deadline exceeded")

    return min(float(requested_seconds), remaining)


async def check_run_control(run_id: UUID) -> ResearchRun:
    async with SessionLocal() as session:
        run = await session.get(ResearchRun, run_id)

        if run is None:
            raise ValueError(f"Unknown research run: {run_id}")

        try:
            ensure_run_active(run.status, run.deadline_at)
        except RunTimedOut:
            if run.status != RunStatus.TIMED_OUT:
                run.status = RunStatus.TIMED_OUT
                run.finished_at = datetime.now(UTC)
                run.error = "Research run deadline exceeded"
                await session.commit()
            raise

        return run


async def run_controlled(
    run_id: UUID,
    operation: Awaitable[T],
    timeout_seconds: float,
    poll_seconds: float = 0.5,
) -> T:
    """
    Run an awaitable while polling PostgreSQL for cancellation
    and deadline state.
    """
    try:
        run = await check_run_control(run_id)
    except Exception:
        if inspect.iscoroutine(operation):
            operation.close()
        raise

    timeout = bounded_timeout(run.deadline_at, timeout_seconds)
    task = asyncio.create_task(operation)
    loop = asyncio.get_running_loop()
    expires_at = loop.time() + timeout

    try:
        while True:
            remaining = expires_at - loop.time()

            if remaining <= 0:
                raise asyncio.TimeoutError

            done, _ = await asyncio.wait(
                {task},
                timeout=min(poll_seconds, remaining),
                return_when=asyncio.FIRST_COMPLETED,
            )

            if task in done:
                return task.result()

            await check_run_control(run_id)
    finally:
        if not task.done():
            task.cancel()

            with suppress(asyncio.CancelledError):
                await task