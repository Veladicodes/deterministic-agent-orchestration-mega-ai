from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_session
from api.dependencies.redis import get_redis

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check(
    session: AsyncSession = Depends(get_session), redis=Depends(get_redis)
) -> dict:
    """Health endpoint that checks DB and Redis connectivity.

    Returns a small diagnostic map to help orchestrators and developers.
    """
    resp = {"api": "ok", "db": "unavailable", "redis": "unavailable"}

    try:
        await session.execute(text("SELECT 1"))
        resp["db"] = "ok"
    except Exception:
        resp["db"] = "error"

    try:
        await redis.ping()
        resp["redis"] = "ok"
    except Exception:
        resp["redis"] = "error"

    return resp
