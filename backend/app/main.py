"""
SURVEYOR — FastAPI application entry point.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.router import api_router
from app.api.interviews import router as interviews_router
from app.api.monitor import router as monitor_router
from app.api.twilio import router as twilio_router
from app.config import settings
from app.database import engine, get_db
from app.redis import close_redis, get_redis


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle hook."""
    # ── Startup ──
    # Verify Redis is reachable
    redis = await get_redis()
    await redis.ping()

    yield

    # ── Shutdown ──
    await engine.dispose()
    await close_redis()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ── CORS (permissive for development) ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routes ───────────────────────────────────────────────
app.include_router(api_router)

# ── WebSocket Routes (outside /api prefix) ───────────────────
app.include_router(interviews_router)
app.include_router(monitor_router)

# ── Twilio Routes (voice webhook + media streams WebSocket) ──
app.include_router(twilio_router)


# ── Public Widget Config (no auth required) ──────────────────
@app.get("/api/widget/{widget_key}", tags=["widget"])
async def widget_config(widget_key: str, db: AsyncSession = Depends(get_db)):
    """
    Public endpoint for the interview widget to fetch its configuration.
    Returns title, description, colour, participant ID mode, etc.
    """
    from app.models.agent import Agent, AgentStatus as AS

    result = await db.execute(
        select(Agent).where(
            Agent.widget_key == widget_key,
            Agent.status == AS.ACTIVE.value,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Agent not found or inactive")

    return {
        "widget_key": agent.widget_key,
        "widget_title": agent.widget_title,
        "widget_description": agent.widget_description,
        "widget_primary_color": agent.widget_primary_color or "#111827",
        "widget_listening_message": agent.widget_listening_message or "Agent is listening…",
        "participant_id_mode": agent.participant_id_mode.value
            if hasattr(agent.participant_id_mode, "value")
            else agent.participant_id_mode,
        "welcome_message": agent.welcome_message,
        "language": agent.language,
    }


# ── Health Check ─────────────────────────────────────────────
@app.get("/api/health", tags=["system"])
async def health_check():
    """
    Verify that the API, database, and Redis are all reachable.
    Returns service-level status for each dependency.
    """
    status: dict[str, str] = {"api": "ok"}

    # Check PostgreSQL
    try:
        async with engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
        status["database"] = "ok"
    except Exception as exc:
        status["database"] = f"error: {exc}"

    # Check Redis
    try:
        redis = await get_redis()
        await redis.ping()
        status["redis"] = "ok"
    except Exception as exc:
        status["redis"] = f"error: {exc}"

    healthy = all(v == "ok" for v in status.values())
    return {"healthy": healthy, "services": status}
