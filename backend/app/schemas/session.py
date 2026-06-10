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
    adaptive_active: bool = False
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


# ── Engagement metrics ───────────────────────────────────────────────────────

class EngagementTurnRead(BaseModel):
    transcript_sequence: int
    response_latency_ms: Optional[int] = None
    voiced_ms: Optional[int] = None
    word_count: Optional[int] = None
    char_count: Optional[int] = None
    speech_rate_wpm: Optional[float] = None
    filler_count: Optional[int] = None
    rms_energy: Optional[float] = None
    score: Optional[float] = None
    label: Optional[str] = None
    flags: list[str] = []

    model_config = {"from_attributes": True}


class EngagementEventRead(BaseModel):
    transcript_sequence: Optional[int] = None
    event_type: str
    score_at_event: Optional[float] = None

    model_config = {"from_attributes": True}


class AdaptiveActionRead(BaseModel):
    transcript_sequence: Optional[int] = None
    trigger: str
    action: str
    mode: str
    detail: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EngagementSummaryRead(BaseModel):
    session_id: UUID
    turn_count: int = 0
    average_score: Optional[float] = None
    label: Optional[str] = None
    average_latency_ms: Optional[int] = None
    average_words: Optional[float] = None
    low_engagement_turns: int = 0
    turns: list[EngagementTurnRead] = []
    events: list[EngagementEventRead] = []
    adaptive_active: bool = False
    adaptive_actions: list[AdaptiveActionRead] = []


class SessionDetailRead(SessionRead):
    """Session with transcript entries."""
    entries: list[TranscriptEntryRead] = []
