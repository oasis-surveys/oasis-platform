"""
Tests for the Redis session manager.

Uses fakeredis — no real Redis server needed.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.models.session import SessionStatus


class TestSessionManager:
    @pytest_asyncio.fixture(autouse=True)
    async def setup_redis(self, fake_redis):
        """Inject fake Redis into the session manager."""
        self.redis = fake_redis
        with patch("app.session_manager.get_redis", return_value=fake_redis):
            yield

    async def test_register_session(self):
        from app.session_manager import register_session

        session_id = uuid.uuid4()
        agent_id = uuid.uuid4()

        await register_session(
            session_id=session_id,
            agent_id=agent_id,
            max_duration_seconds=300,
        )

        # Verify the session key exists in Redis
        key = f"oasis:session:{session_id}"
        data = await self.redis.get(key)
        assert data is not None

        # Verify it's in the active set
        is_member = await self.redis.sismember(
            "oasis:active_sessions", str(session_id)
        )
        assert is_member

    async def test_unregister_session(self):
        from app.session_manager import register_session, unregister_session

        session_id = uuid.uuid4()
        agent_id = uuid.uuid4()

        await register_session(session_id, agent_id)
        await unregister_session(session_id)

        key = f"oasis:session:{session_id}"
        data = await self.redis.get(key)
        assert data is None

        is_member = await self.redis.sismember(
            "oasis:active_sessions", str(session_id)
        )
        assert not is_member

    async def test_get_active_session_count(self):
        from app.session_manager import (
            register_session,
            get_active_session_count,
        )

        s1 = uuid.uuid4()
        s2 = uuid.uuid4()
        agent = uuid.uuid4()

        await register_session(s1, agent)
        await register_session(s2, agent)

        count = await get_active_session_count()
        assert count == 2

    async def test_get_active_session_ids(self):
        from app.session_manager import (
            register_session,
            get_active_session_ids,
        )

        s1 = uuid.uuid4()
        agent = uuid.uuid4()

        await register_session(s1, agent)

        ids = await get_active_session_ids()
        assert str(s1) in ids
