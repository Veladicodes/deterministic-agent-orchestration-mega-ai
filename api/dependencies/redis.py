from functools import lru_cache

import redis.asyncio as aioredis

from shared.settings import get_settings

settings = get_settings()


@lru_cache(maxsize=1)
def get_redis_client() -> aioredis.Redis:
    """Return a cached Redis client instance for dependency injection."""
    return aioredis.from_url(settings.redis_url)


async def get_redis():
    """FastAPI dependency that yields a redis client.

    The client is not closed here because it's reused across requests.
    """
    yield get_redis_client()
