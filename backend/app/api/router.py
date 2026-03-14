"""
SURVEYOR — Top-level API router.

Aggregates all sub-routers under the /api prefix.
"""

from fastapi import APIRouter

from app.api.studies import router as studies_router
from app.api.agents import router as agents_router
from app.api.sessions import router as sessions_router
from app.api.analytics import router as analytics_router
from app.api.participants import router as participants_router

api_router = APIRouter(prefix="/api")

api_router.include_router(studies_router)
api_router.include_router(agents_router)
api_router.include_router(sessions_router)
api_router.include_router(analytics_router)
api_router.include_router(participants_router)
