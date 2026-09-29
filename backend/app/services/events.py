import json
from collections.abc import AsyncIterator

from redis.asyncio import Redis

from app.core.config import get_settings

settings = get_settings()


def event_stream_key(run_id: str) -> str:
    return f"research:run:{run_id}:events"


async def publish_event(run_id: str, event_type: str, payload: dict) -> None:
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await client.xadd(
            event_stream_key(run_id),
            {"event": event_type, "data": json.dumps(payload)},
            maxlen=2000,
            approximate=True,
        )
    finally:
        await client.aclose()


async def stream_events(run_id: str, last_event_id: str = "0-0") -> AsyncIterator[str]:
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    stream_id = last_event_id
    try:
        while True:
            results = await client.xread(
                {event_stream_key(run_id): stream_id}, block=15_000, count=20
            )
            if not results:
                yield ": keep-alive\n\n"
                continue
            for _, entries in results:
                for entry_id, fields in entries:
                    stream_id = entry_id
                    yield (f"id: {entry_id}\nevent: {fields['event']}\ndata: {fields['data']}\n\n")
    finally:
        await client.aclose()
