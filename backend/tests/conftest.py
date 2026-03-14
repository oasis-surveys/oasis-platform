"""
OASIS — Shared test fixtures.

Provides:
- An in-memory SQLite database for fast, isolated tests.
- A fake Redis client (no real Redis server needed).
- A configured FastAPI TestClient with dependency overrides.
- Factory fixtures for creating test data (studies, agents, sessions).
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, String, Text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ---------------------------------------------------------------------------
# Override settings BEFORE importing anything from app.*
# ---------------------------------------------------------------------------
import os

os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-jwt")
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key")
os.environ.setdefault("DEEPGRAM_API_KEY", "dg-test-fake-key")
os.environ.setdefault("ELEVENLABS_API_KEY", "el-test-fake-key")
os.environ.setdefault("GOOGLE_API_KEY", "goog-test-fake-key")

# ---------------------------------------------------------------------------
# Patch pgvector's Vector type BEFORE importing models
# ---------------------------------------------------------------------------
# SQLite doesn't support pgvector's Vector type. Replace it with Text
# so that table creation works in the test database.
try:
    import pgvector.sqlalchemy as _pgv

    class _FakeVector(Text):
        """Drop-in replacement for pgvector.sqlalchemy.Vector for SQLite."""
        cache_ok = True

        def __init__(self, *args, **kwargs):
            super().__init__()

    _pgv.Vector = _FakeVector  # type: ignore[assignment]
except ImportError:
    pass

from app.models.base import Base
from app.database import get_db
from app.redis import get_redis, close_redis

# ---------------------------------------------------------------------------
# Database — async SQLite in-memory
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture()
async def db_engine():
    """Create an async SQLite engine scoped to each test."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture()
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session that rolls back after each test."""
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture()
async def db_session_factory(db_engine):
    """Return a session factory for tests that need to create their own sessions."""
    return async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )


# ---------------------------------------------------------------------------
# Redis — fake in-memory implementation
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def fake_redis():
    """Provide a fake Redis client (no server needed)."""
    try:
        import fakeredis.aioredis

        redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        yield redis
        await redis.aclose()
    except ImportError:
        # Fallback: use a simple mock
        redis = AsyncMock()
        redis.ping = AsyncMock(return_value=True)
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        redis.delete = AsyncMock(return_value=1)
        redis.hget = AsyncMock(return_value=None)
        redis.hgetall = AsyncMock(return_value={})
        redis.hset = AsyncMock(return_value=1)
        redis.hdel = AsyncMock(return_value=1)
        redis.sadd = AsyncMock(return_value=1)
        redis.srem = AsyncMock(return_value=1)
        redis.scard = AsyncMock(return_value=0)
        redis.smembers = AsyncMock(return_value=set())
        redis.sismember = AsyncMock(return_value=False)
        redis.exists = AsyncMock(return_value=False)
        redis.keys = AsyncMock(return_value=[])
        redis.publish = AsyncMock(return_value=1)
        yield redis


# ---------------------------------------------------------------------------
# FastAPI app with dependency overrides
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def app(db_engine, fake_redis) -> FastAPI:
    """Create a FastAPI app with test DB and Redis injected."""
    from app.main import app as _app

    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _override_get_redis():
        return fake_redis

    _app.dependency_overrides[get_db] = _override_get_db
    _app.dependency_overrides[get_redis] = _override_get_redis

    # Also patch the module-level session factory used by modules that
    # import it directly (e.g. Twilio endpoints, realtime module).
    import app.database as _db_module
    import app.api.twilio as _twilio_module

    _original_factory = _db_module.async_session_factory
    _db_module.async_session_factory = session_factory
    _twilio_original_factory = _twilio_module.async_session_factory
    _twilio_module.async_session_factory = session_factory

    # Patch the get_redis function used outside of FastAPI DI
    # Multiple modules import get_redis directly, so we patch all of them
    async def _patched_get_redis():
        return fake_redis

    import app.redis as _redis_module
    import app.api.settings as _settings_module
    import app.session_manager as _sm_module
    import app.realtime as _realtime_module

    _originals = {
        "redis": _redis_module.get_redis,
        "settings": _settings_module.get_redis,
        "session_manager": _sm_module.get_redis,
        "realtime": _realtime_module.get_redis,
    }

    _redis_module.get_redis = _patched_get_redis
    _settings_module.get_redis = _patched_get_redis
    _sm_module.get_redis = _patched_get_redis
    _realtime_module.get_redis = _patched_get_redis

    yield _app

    _app.dependency_overrides.clear()
    _db_module.async_session_factory = _original_factory
    _twilio_module.async_session_factory = _twilio_original_factory
    _redis_module.get_redis = _originals["redis"]
    _settings_module.get_redis = _originals["settings"]
    _sm_module.get_redis = _originals["session_manager"]
    _realtime_module.get_redis = _originals["realtime"]


@pytest_asyncio.fixture()
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """An async HTTP client that talks to the test FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture()
async def auth_client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """An authenticated async HTTP client (gets a token first)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Get a token (auth is disabled by default so any creds work)
        resp = await ac.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        token = resp.json()["token"]
        ac.headers["Authorization"] = f"Bearer {token}"
        yield ac


# ---------------------------------------------------------------------------
# Data factories
# ---------------------------------------------------------------------------

@pytest.fixture
def make_study():
    """Factory fixture to create Study model instances."""
    from app.models.study import Study, StudyStatus

    def _make(
        title: str = "Test Study",
        description: str = "A test study",
        status: StudyStatus = StudyStatus.DRAFT,
    ) -> Study:
        return Study(
            id=uuid.uuid4(),
            title=title,
            description=description,
            status=status,
        )

    return _make


@pytest.fixture
def make_agent():
    """Factory fixture to create Agent model instances."""
    from app.models.agent import Agent, AgentStatus, PipelineType

    def _make(
        study_id: uuid.UUID | None = None,
        name: str = "Test Agent",
        status: AgentStatus = AgentStatus.ACTIVE,
        pipeline_type: PipelineType = PipelineType.MODULAR,
        llm_model: str = "openai/gpt-4o-mini",
        system_prompt: str = "You are a test agent.",
        welcome_message: str = "Hello!",
    ) -> Agent:
        return Agent(
            id=uuid.uuid4(),
            study_id=study_id or uuid.uuid4(),
            name=name,
            status=status,
            pipeline_type=pipeline_type,
            llm_model=llm_model,
            system_prompt=system_prompt,
            welcome_message=welcome_message,
        )

    return _make


@pytest.fixture
def make_session():
    """Factory fixture to create Session model instances."""
    from app.models.session import Session, SessionStatus

    def _make(
        agent_id: uuid.UUID | None = None,
        status: SessionStatus = SessionStatus.ACTIVE,
        participant_id: str = "test-participant",
    ) -> Session:
        return Session(
            id=uuid.uuid4(),
            agent_id=agent_id or uuid.uuid4(),
            status=status,
            participant_id=participant_id,
        )

    return _make
