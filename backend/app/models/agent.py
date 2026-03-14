"""
SURVEYOR — Agent model.

An Agent is a configured conversational AI interviewer belonging to a Study.
It holds the prompt, model selection, voice settings, and pipeline type.
"""

import enum
import secrets
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PipelineType(str, enum.Enum):
    MODULAR = "modular"            # Path B: STT → LLM → TTS
    VOICE_TO_VOICE = "voice_to_voice"  # Path A: Direct multimodal


class AgentStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"


class ParticipantIdMode(str, enum.Enum):
    RANDOM = "random"       # Auto-generate on call start
    PREDEFINED = "predefined"  # Admin uploads a list; each gets a unique link
    INPUT = "input"         # Participant enters ID in widget before starting


def _generate_widget_key() -> str:
    return secrets.token_urlsafe(16)


class Agent(Base):
    __tablename__ = "agents"

    # ── Ownership ──
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("studies.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ── Identity ──
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[AgentStatus] = mapped_column(
        Enum(
            AgentStatus,
            name="agent_status",
            values_callable=lambda e: [member.value for member in e],
        ),
        default=AgentStatus.DRAFT,
        server_default=AgentStatus.DRAFT.value,
    )

    # ── Prompt / Behaviour ──
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    welcome_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default="Hello, thank you for participating in this study.",
    )

    # ── Pipeline ──
    pipeline_type: Mapped[PipelineType] = mapped_column(
        Enum(
            PipelineType,
            name="pipeline_type",
            values_callable=lambda e: [member.value for member in e],
        ),
        default=PipelineType.MODULAR,
        server_default=PipelineType.MODULAR.value,
    )

    # ── LLM ──
    llm_model: Mapped[str] = mapped_column(
        String(255), nullable=False, default="openai/gpt-4o"
    )

    # ── STT (Speech-to-Text) ──
    stt_provider: Mapped[str] = mapped_column(
        String(100), nullable=False, default="deepgram"
    )
    stt_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── TTS (Text-to-Speech) ──
    tts_provider: Mapped[str] = mapped_column(
        String(100), nullable=False, default="elevenlabs"
    )
    tts_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tts_voice: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Interview settings ──
    language: Mapped[str] = mapped_column(String(10), default="en", server_default="en")
    max_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Participant identification ──
    participant_id_mode: Mapped[ParticipantIdMode] = mapped_column(
        Enum(
            ParticipantIdMode,
            name="participant_id_mode",
            values_callable=lambda e: [member.value for member in e],
        ),
        default=ParticipantIdMode.RANDOM,
        server_default=ParticipantIdMode.RANDOM.value,
    )

    # ── Widget customisation ──
    widget_key: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
        default=_generate_widget_key,
    )
    widget_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    widget_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    widget_primary_color: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default="#111827"
    )
    widget_listening_message: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default="Agent is listening…"
    )

    # ── Telephony (Twilio) ──
    twilio_phone_number: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )

    # ── Relationships ──
    study = relationship("Study", back_populates="agents")
    participant_identifiers = relationship(
        "ParticipantIdentifier",
        back_populates="agent",
        cascade="all, delete-orphan",
    )


class ParticipantIdentifier(Base):
    """
    Pre-defined participant identifiers managed by the researcher.
    Each gets a unique link: /interview/{widget_key}?pid={identifier}
    """
    __tablename__ = "participant_identifiers"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    used: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Relationships ──
    agent = relationship("Agent", back_populates="participant_identifiers")
    session = relationship("Session")
