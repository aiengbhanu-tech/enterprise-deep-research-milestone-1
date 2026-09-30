import functools
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from langgraph.errors import GraphInterrupt

from app.db.session import SessionLocal
from app.models.trace import ExecutionTrace


def _run_uuid(state: dict) -> UUID | None:
    try:
        return UUID(str(state.get("run_id")))
    except (TypeError, ValueError):
        return None


def summarize(value: Any) -> dict:
    if not isinstance(value, dict):
        return {"type": type(value).__name__}
    summary: dict[str, Any] = {"keys": sorted(value.keys())}
    for key in ("evidence", "sources", "coverage", "gaps", "contradictions", "sections"):
        if isinstance(value.get(key), list):
            summary[f"{key}_count"] = len(value[key])
    for key in ("status", "iteration", "repair_attempts"):
        if key in value:
            summary[key] = value[key]
    return summary


def traced_node(
    node_name: str, span_type: str = "agent"
) -> Callable[[Callable[[dict], Awaitable[dict]]], Callable[[dict], Awaitable[dict]]]:
    def decorator(function: Callable[[dict], Awaitable[dict]]):
        @functools.wraps(function)
        async def wrapper(state: dict) -> dict:
            run_id = _run_uuid(state)
            if run_id is None:
                return await function(state)

            started = datetime.now(UTC)
            started_perf = time.perf_counter()
            async with SessionLocal() as session:
                span = ExecutionTrace(
                    run_id=run_id,
                    trace_id=str(state.get("trace_id") or run_id),
                    node_name=node_name,
                    span_type=span_type,
                    status="running",
                    attempt=1,
                    started_at=started,
                    input_summary=summarize(state),
                    output_summary={},
                    span_attributes={},
                )
                session.add(span)
                await session.commit()
                await session.refresh(span)
                span_id = span.id

            try:
                result = await function(state)
            except GraphInterrupt:
                ended = datetime.now(UTC)
                async with SessionLocal() as session:
                    span = await session.get(ExecutionTrace, span_id)
                    if span:
                        span.status = "interrupted"
                        span.ended_at = ended
                        span.latency_ms = int((time.perf_counter() - started_perf) * 1000)
                        span.output_summary = {"interrupt": True}
                        await session.commit()
                raise
            except Exception as exc:
                ended = datetime.now(UTC)
                async with SessionLocal() as session:
                    span = await session.get(ExecutionTrace, span_id)
                    if span:
                        span.status = "failed"
                        span.ended_at = ended
                        span.latency_ms = int((time.perf_counter() - started_perf) * 1000)
                        span.error_type = type(exc).__name__
                        span.error_message = str(exc)[:2000]
                        await session.commit()
                raise

            ended = datetime.now(UTC)
            async with SessionLocal() as session:
                span = await session.get(ExecutionTrace, span_id)
                if span:
                    span.status = "succeeded"
                    span.ended_at = ended
                    span.latency_ms = int((time.perf_counter() - started_perf) * 1000)
                    span.output_summary = summarize(result)
                    await session.commit()
            return result

        return wrapper

    return decorator
