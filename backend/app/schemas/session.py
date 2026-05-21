"""Pydantic schemas for Session and TranscriptEntry resources."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.models.session import SessionStatus, SpeakerRole


# ── TranscriptEntry ──────────────────────────────────────────────────────────

class TranscriptEntryRead(BaseModel):
    id: UUID
    session_id: UUID
    role: SpeakerRole
    content: str
    sequence: int
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    spoken_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Session ──────────────────────────────────────────────────────────────────

class SessionRead(BaseModel):
    id: UUID
    agent_id: UUID
    status: SessionStatus
    duration_seconds: Optional[float] = None
    total_tokens: Optional[int] = None
    participant_id: Optional[str] = None
    ended_at: Optional[datetime] = None
    audio_recording_enabled: bool = False
    audio_storage_uri: Optional[str] = None
    audio_recording_status: str = "none"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AudioTurnRead(BaseModel):
    sequence: int
    role: str
    filename: str
    duration_ms: Optional[int] = None
    content_preview: Optional[str] = None


class SessionAudioManifestRead(BaseModel):
    session_id: UUID
    storage_uri: Optional[str] = None
    recording_status: str
    turns: list[AudioTurnRead] = []


class SessionDetailRead(SessionRead):
    """Session with transcript entries."""
    entries: list[TranscriptEntryRead] = []
