from fastapi import APIRouter
from redis.asyncio import Redis
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import get_settings

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
async def health(session: DbSession) -> dict:
    dependencies: dict[str, str] = {}
    try:
        await session.execute(text("SELECT 1"))
        dependencies["postgres"] = "ok"
    except Exception:
        dependencies["postgres"] = "unavailable"
    redis = Redis.from_url(settings.redis_url)
    try:
        await redis.ping()
        dependencies["redis"] = "ok"
    except Exception:
        dependencies["redis"] = "unavailable"
    finally:
        await redis.aclose()
    status = "ok" if all(value == "ok" for value in dependencies.values()) else "degraded"
    return {"status": status, "dependencies": dependencies}
