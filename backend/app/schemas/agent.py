"""
OASIS — Pydantic schemas for Agent CRUD.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.agent import AgentModality, AgentStatus, InterviewMode, ParticipantIdMode, PipelineType


# ── Structured Interview Guide Sub-Schemas ───────────────────


class InterviewQuestion(BaseModel):
    """A single question in the structured interview guide."""
    text: str = Field(..., min_length=1, description="The main question text")
    probes: list[str] = Field(
        default_factory=list,
        description="Example follow-up probes for deeper exploration",
    )
    max_follow_ups: int = Field(
        3,
        ge=0,
        le=10,
        description="Maximum follow-up exchanges before moving on",
    )
    transition: str | None = Field(
        None,
        description="Optional transition text when moving to the next question",
    )


class InterviewGuide(BaseModel):
    """Structured interview protocol — a list of questions with probes."""
    questions: list[InterviewQuestion] = Field(
        ...,
        min_length=1,
        description="Ordered list of interview questions",
    )
    closing_message: str | None = Field(
        "Thank you for your time. This concludes our interview.",
        description="Message spoken after the last question is complete",
    )


# ── Request Schemas ──────────────────────────────────────────


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    modality: AgentModality = AgentModality.VOICE
    avatar: str | None = Field("neutral", max_length=50)
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

    # Interview mode
    interview_mode: InterviewMode = InterviewMode.FREE_FORM
    interview_guide: InterviewGuide | None = None

    # Silence handling
    silence_timeout_seconds: int | None = None
    silence_prompt: str | None = None

    # Telephony
    twilio_phone_number: str | None = None


class AgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    modality: AgentModality | None = None
    avatar: str | None = None
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

    # Interview mode
    interview_mode: InterviewMode | None = None
    interview_guide: InterviewGuide | None = None

    silence_timeout_seconds: int | None = None
    silence_prompt: str | None = None

    twilio_phone_number: str | None = None


# ── Response Schemas ─────────────────────────────────────────


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    study_id: UUID
    name: str
    modality: AgentModality
    avatar: str | None
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

    interview_mode: InterviewMode
    interview_guide: dict | None

    silence_timeout_seconds: int | None
    silence_prompt: str | None

    twilio_phone_number: str | None

    created_at: datetime
    updated_at: datetime


class AgentList(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    study_id: UUID
    name: str
    modality: AgentModality
    avatar: str | None
    status: AgentStatus
    pipeline_type: PipelineType
    llm_model: str
    language: str
    widget_key: str
    participant_id_mode: ParticipantIdMode
    interview_mode: InterviewMode
    created_at: datetime
