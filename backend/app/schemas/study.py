"""
OASIS — Pydantic schemas for Study CRUD.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.study import StudyStatus


# ── Request Schemas ──────────────────────────────────────────


class StudyCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    status: StudyStatus = StudyStatus.DRAFT


class StudyUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    status: StudyStatus | None = None


# ── Response Schemas ─────────────────────────────────────────


class StudyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    status: StudyStatus
    created_at: datetime
    updated_at: datetime


class StudyList(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    status: StudyStatus
    created_at: datetime
