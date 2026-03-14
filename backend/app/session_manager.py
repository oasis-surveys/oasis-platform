"""
SURVEYOR — Redis-based active session manager.

Tracks active interview sessions in Redis with TTL-based automatic expiry.
A background task periodically checks for zombie sessions and cleans them up.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.redis import get_redis
from app.database import async_session_factory
from app.models.session import Session, SessionStatus

# Redis key prefixes
_SESSION_KEY = "surveyor:session:{session_id}"
_ACTIVE_SET = "surveyor:active_sessions"

# Default TTL for a session key — acts as an absolute safety net.
# Even if the pipeline crashes without cleanup, Redis will expire the key.
_DEFAULT_TTL_SECONDS = 7200 + 120  # 2 hours + 2 min buffer


async def register_session(
    session_id: uuid.UUID,
    agent_id: uuid.UUID,
    max_duration_seconds: Optional[int] = None,
) -> None:
    """Register a new active session in Redis."""
    redis = await get_redis()
    key = _SESSION_KEY.format(session_id=session_id)
    ttl = (max_duration_seconds or 7200) + 120  # Add buffer

    data = {
        "session_id": str(session_id),
        "agent_id": str(agent_id),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "max_duration_seconds": max_duration_seconds,
    }

    await redis.set(key, json.dumps(data), ex=ttl)
    await redis.sadd(_ACTIVE_SET, str(session_id))

    logger.debug(f"Session registered in Redis: {session_id} (TTL={ttl}s)")


async def unregister_session(session_id: uuid.UUID) -> None:
    """Remove a session from Redis tracking."""
    redis = await get_redis()
    key = _SESSION_KEY.format(session_id=session_id)

    await redis.delete(key)
    await redis.srem(_ACTIVE_SET, str(session_id))

    logger.debug(f"Session unregistered from Redis: {session_id}")


async def get_active_session_count() -> int:
    """Return the number of currently tracked active sessions."""
    redis = await get_redis()
    return await redis.scard(_ACTIVE_SET)


async def get_active_session_ids() -> list[str]:
    """Return all active session IDs."""
    redis = await get_redis()
    return list(await redis.smembers(_ACTIVE_SET))


async def cleanup_zombie_sessions() -> int:
    """
    Check for sessions that Redis has expired (key gone) but are still
    in the active set. Mark them as timed_out in PostgreSQL.

    Returns the number of cleaned-up sessions.
    """
    redis = await get_redis()
    active_ids = await redis.smembers(_ACTIVE_SET)
    cleaned = 0

    for sid in active_ids:
        key = _SESSION_KEY.format(session_id=sid)
        exists = await redis.exists(key)

        if not exists:
            # Redis key expired — session should have been cleaned up
            # but wasn't (crash, network issue, etc.)
            logger.warning(f"Zombie session detected: {sid} — cleaning up")

            try:
                async with async_session_factory() as db:
                    session = await db.get(Session, uuid.UUID(sid))
                    if session and session.status == SessionStatus.ACTIVE:
                        session.status = SessionStatus.TIMED_OUT
                        session.ended_at = datetime.now(timezone.utc)
                        if session.created_at:
                            session.duration_seconds = (
                                session.ended_at - session.created_at
                            ).total_seconds()
                        await db.commit()
                        logger.info(f"Zombie session {sid} marked as timed_out")
            except Exception as e:
                logger.error(f"Failed to clean up zombie session {sid}: {e}")

            await redis.srem(_ACTIVE_SET, sid)
            cleaned += 1

    return cleaned


async def session_cleanup_loop(interval_seconds: int = 60) -> None:
    """
    Background task that runs periodically to clean up zombie sessions.

    Should be started as an asyncio task during app lifespan.
    """
    logger.info(
        f"Session cleanup loop started (interval={interval_seconds}s)"
    )

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            cleaned = await cleanup_zombie_sessions()
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} zombie session(s)")
        except asyncio.CancelledError:
            logger.info("Session cleanup loop cancelled")
            break
        except Exception as e:
            logger.error(f"Session cleanup loop error: {e}")
            await asyncio.sleep(10)  # Back off on error
