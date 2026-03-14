"""
SURVEYOR — Pydantic schemas for Participant Identifiers.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ParticipantIdentifierCreate(BaseModel):
    identifier: str = Field(..., min_length=1, max_length=255)
    label: str | None = None


class ParticipantIdentifierBulkCreate(BaseModel):
    """Create multiple participant identifiers at once."""
    identifiers: list[str] = Field(..., min_length=1)


class ParticipantIdentifierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    identifier: str
    label: str | None
    used: bool
    session_id: UUID | None
    created_at: datetime
    updated_at: datetime
