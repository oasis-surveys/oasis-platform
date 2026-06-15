"""
OASIS — Pydantic schemas for Agent CRUD.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


# ── Engagement config sub-schemas ────────────────────────────


class EngagementWeights(BaseModel):
    length: float = Field(0.35, ge=0, le=1)
    latency: float = Field(0.25, ge=0, le=1)
    rate: float = Field(0.15, ge=0, le=1)
    fillers: float = Field(0.15, ge=0, le=1)
    energy: float = Field(0.10, ge=0, le=1)


class EngagementConfig(BaseModel):
    """Per-agent tuning for the engagement scorer and event detector."""
    window_size: int = Field(3, ge=2, le=10, description="Turns for streak/event detection")
    low_threshold: float = Field(0.34, ge=0, le=1)
    high_threshold: float = Field(0.67, ge=0, le=1)
    long_latency_ms: int = Field(4000, ge=500, le=30000)
    short_answer_words: int = Field(3, ge=1, le=20)
    weights: EngagementWeights = Field(default_factory=EngagementWeights)


# ── Adaptive behavior sub-schemas ────────────────────────────

ADAPTIVE_TRIGGERS = (
    "sustained_disengagement",
    "positive_engagement_streak",
    "recovery_after_dip",
    "long_latency",
    "very_short_answer",
    "high_filler",
)

ADAPTIVE_ACTIONS = (
    "offer_break",
    "soften_next_probe",
    "encourage_elaboration",
    "acknowledge_effort",
    "privacy_check",
    "slow_down",
    "reset_pace",
)


class AdaptiveRule(BaseModel):
    on: str = Field(..., description="Trigger event or per-turn flag")
    action: str = Field(..., description="Curated action id")
    custom_instruction: str | None = Field(None, max_length=2000)
    cooldown_seconds: int = Field(0, ge=0, le=3600)
    params: dict = Field(default_factory=dict)

    @field_validator("on")
    @classmethod
    def _valid_trigger(cls, v: str) -> str:
        if v not in ADAPTIVE_TRIGGERS:
            raise ValueError(f"unknown trigger: {v}")
        return v

    @field_validator("action")
    @classmethod
    def _valid_action(cls, v: str) -> str:
        if v not in ADAPTIVE_ACTIONS:
            raise ValueError(f"unknown action: {v}")
        return v


class AdaptivePolicy(BaseModel):
    """Per-agent adaptive behavior policy. Defaults to safe shadow mode."""
    mode: str = Field("shadow", pattern="^(shadow|live)$")
    rules: list[AdaptiveRule] = Field(default_factory=list)


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

    status: AgentStatus = AgentStatus.ACTIVE

    # Participant ID
    participant_id_mode: ParticipantIdMode = ParticipantIdMode.RANDOM

    # Widget customisation
    widget_title: str | None = None
    widget_description: str | None = None
    widget_primary_color: str | None = "#111827"
    widget_listening_message: str | None = "Agent is listening…"
    widget_show_progress: bool = False

    # Interview mode
    interview_mode: InterviewMode = InterviewMode.FREE_FORM
    interview_guide: InterviewGuide | None = None

    # Silence handling
    silence_timeout_seconds: int | None = None
    silence_prompt: str | None = None

    # Telephony
    twilio_phone_number: str | None = None

    # Audio recording (voice web interviews; per-agent opt-in)
    store_audio: bool = False

    # Engagement metrics (voice web interviews; per-agent opt-in, observational)
    track_engagement: bool = False
    engagement_config: EngagementConfig | None = None

    # Adaptive behavior (requires engagement; defaults to shadow mode)
    adaptive_enabled: bool = False
    adaptive_policy: AdaptivePolicy | None = None


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
    widget_show_progress: bool | None = None

    # Interview mode
    interview_mode: InterviewMode | None = None
    interview_guide: InterviewGuide | None = None

    silence_timeout_seconds: int | None = None
    silence_prompt: str | None = None

    twilio_phone_number: str | None = None

    store_audio: bool | None = None

    track_engagement: bool | None = None
    engagement_config: EngagementConfig | None = None
    adaptive_enabled: bool | None = None
    adaptive_policy: AdaptivePolicy | None = None


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
    widget_show_progress: bool

    interview_mode: InterviewMode
    interview_guide: dict | None

    silence_timeout_seconds: int | None
    silence_prompt: str | None

    twilio_phone_number: str | None

    store_audio: bool

    track_engagement: bool
    engagement_config: dict | None
    adaptive_enabled: bool
    adaptive_policy: dict | None

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
    stt_provider: str
    stt_model: str | None
    tts_provider: str
    tts_model: str | None
    tts_voice: str | None
    language: str
    widget_key: str
    participant_id_mode: ParticipantIdMode
    interview_mode: InterviewMode
    created_at: datetime
