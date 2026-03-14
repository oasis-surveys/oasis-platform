"""
OASIS — Real-time transcript broadcasting via Redis Pub/Sub.

When a pipeline logs a transcript entry, it publishes to a Redis channel.
Researcher monitor WebSockets subscribe to the same channel and receive
updates in real-time.
"""

import json
from typing import Any

from loguru import logger
from redis.asyncio import Redis

from app.redis import get_redis


def _channel(session_id: str) -> str:
    """Redis channel name for a given session."""
    return f"oasis:transcript:{session_id}"


async def publish_transcript_event(session_id: str, payload: dict[str, Any]) -> None:
    """Publish a transcript entry to the Redis channel for the given session."""
    redis: Redis = await get_redis()
    channel = _channel(str(session_id))
    try:
        await redis.publish(channel, json.dumps(payload))
    except Exception as exc:
        logger.warning(f"Failed to publish transcript event: {exc}")


async def subscribe_transcript(session_id: str):
    """
    Async generator that yields transcript events for a session.

    Usage:
        async for event in subscribe_transcript(session_id):
            await websocket.send_json(event)
    """
    from redis.asyncio import from_url
    from app.config import settings

    # Pub/Sub requires a dedicated connection (not the shared one used for
    # commands), so we create a fresh client for each subscriber.
    redis: Redis = from_url(settings.redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    channel = _channel(str(session_id))

    await pubsub.subscribe(channel)
    logger.info(f"Subscribed to transcript channel: {channel}")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    yield data
                except (json.JSONDecodeError, TypeError):
                    continue
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await redis.aclose()
        logger.info(f"Unsubscribed from transcript channel: {channel}")
