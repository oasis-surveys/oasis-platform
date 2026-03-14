"""
SURVEYOR — Pydantic schemas for Agent CRUD.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.agent import AgentStatus, ParticipantIdMode, PipelineType


# ── Request Schemas ──────────────────────────────────────────


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    system_prompt: str = ""
    welcome_message: str | None = "Hello, thank you for participating in this study."

    pipeline_type: PipelineType = PipelineType.MODULAR

    llm_model: str = Field("openai/gpt-4o", max_length=255)

    stt_provider: str = Field("deepgram", max_length=100)
    stt_model: str | None = None

    tts_provider: str = Field("elevenlabs", max_length=100)
    tts_model: str | None = None
    tts_voice: str | None = None

    language: str = Field("en", max_length=10)
    max_duration_seconds: int | None = Field(None, ge=60, le=7200)

    status: AgentStatus = AgentStatus.DRAFT

    # Participant ID
    participant_id_mode: ParticipantIdMode = ParticipantIdMode.RANDOM

    # Widget customisation
    widget_title: str | None = None
    widget_description: str | None = None
    widget_primary_color: str | None = "#111827"
    widget_listening_message: str | None = "Agent is listening…"


class AgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    system_prompt: str | None = None
    welcome_message: str | None = None

    pipeline_type: PipelineType | None = None

    llm_model: str | None = Field(None, max_length=255)

    stt_provider: str | None = Field(None, max_length=100)
    stt_model: str | None = None

    tts_provider: str | None = Field(None, max_length=100)
    tts_model: str | None = None
    tts_voice: str | None = None

    language: str | None = Field(None, max_length=10)
    max_duration_seconds: int | None = Field(None, ge=60, le=7200)

    status: AgentStatus | None = None

    participant_id_mode: ParticipantIdMode | None = None

    widget_title: str | None = None
    widget_description: str | None = None
    widget_primary_color: str | None = None
    widget_listening_message: str | None = None


# ── Response Schemas ─────────────────────────────────────────


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    study_id: UUID
    name: str
    status: AgentStatus
    system_prompt: str
    welcome_message: str | None

    pipeline_type: PipelineType

    llm_model: str

    stt_provider: str
    stt_model: str | None

    tts_provider: str
    tts_model: str | None
    tts_voice: str | None

    language: str
    max_duration_seconds: int | None

    participant_id_mode: ParticipantIdMode

    widget_key: str
    widget_title: str | None
    widget_description: str | None
    widget_primary_color: str | None
    widget_listening_message: str | None

    created_at: datetime
    updated_at: datetime


class AgentList(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    study_id: UUID
    name: str
    status: AgentStatus
    pipeline_type: PipelineType
    llm_model: str
    language: str
    widget_key: str
    participant_id_mode: ParticipantIdMode
    created_at: datetime
