"""
SURVEYOR — Redis connection utility.

Provides an async Redis client for session state, rate limiting,
and call duration timers.
"""

from redis.asyncio import Redis, from_url

from app.config import settings

_redis_client: Redis | None = None


async def get_redis() -> Redis:
    """Return a shared async Redis client (lazy-initialised)."""
    global _redis_client
    if _redis_client is None:
        _redis_client = from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return _redis_client


async def close_redis() -> None:
    """Gracefully close the Redis connection."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
