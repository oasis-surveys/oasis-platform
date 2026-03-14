"""
SURVEYOR — Top-level API router.

Aggregates all sub-routers under the /api prefix.
Protected routes require authentication when AUTH_ENABLED=true.
"""

from fastapi import APIRouter, Depends

from app.auth import require_auth
from app.api.auth import router as auth_router
from app.api.studies import router as studies_router
from app.api.agents import router as agents_router
from app.api.sessions import router as sessions_router
from app.api.analytics import router as analytics_router
from app.api.participants import router as participants_router
from app.api.knowledge import router as knowledge_router
from app.api.settings import router as settings_router

api_router = APIRouter(prefix="/api")

# Public routes (no auth required)
api_router.include_router(auth_router)

# Protected routes (auth required when AUTH_ENABLED=true)
api_router.include_router(studies_router, dependencies=[Depends(require_auth)])
api_router.include_router(agents_router, dependencies=[Depends(require_auth)])
api_router.include_router(sessions_router, dependencies=[Depends(require_auth)])
api_router.include_router(analytics_router, dependencies=[Depends(require_auth)])
api_router.include_router(participants_router, dependencies=[Depends(require_auth)])
api_router.include_router(knowledge_router, dependencies=[Depends(require_auth)])
api_router.include_router(settings_router, dependencies=[Depends(require_auth)])
