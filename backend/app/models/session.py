"""
OASIS — Session and TranscriptEntry models.

A Session represents a single interview between a participant and an agent.
TranscriptEntry holds each diarized (user/agent) utterance within that session.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from app.models.base import Base


class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    ERROR = "error"


class SpeakerRole(str, enum.Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class Session(Base):
    __tablename__ = "sessions"

    # ── Ownership ──
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ── Status ──
    status: Mapped[SessionStatus] = mapped_column(
        Enum(
            SessionStatus,
            name="session_status",
            values_callable=lambda e: [member.value for member in e],
        ),
        default=SessionStatus.ACTIVE,
        server_default=SessionStatus.ACTIVE.value,
    )

    # ── Metrics ──
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Participant metadata ──
    participant_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Relationships ──
    agent = relationship(
        "Agent",
        backref=backref("sessions", cascade="all, delete-orphan", passive_deletes=True),
    )
    entries = relationship(
        "TranscriptEntry",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="TranscriptEntry.sequence",
    )


class TranscriptEntry(Base):
    __tablename__ = "transcript_entries"

    # ── Ownership ──
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ── Content ──
    role: Mapped[SpeakerRole] = mapped_column(
        Enum(
            SpeakerRole,
            name="speaker_role",
            values_callable=lambda e: [member.value for member in e],
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # ── Ordering ──
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Token metrics (for agent responses) ──
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Timestamp ──
    spoken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # ── Relationships ──
    session = relationship("Session", back_populates="entries")


async def aggregate_session_tokens(db: AsyncSession, session_id: uuid.UUID) -> int:
    """Return the sum of prompt + completion tokens across a session's entries.

    Returns ``0`` when no transcript entries have token counts. This is used by
    every interview-finalize path to populate ``Session.total_tokens`` so the
    dashboard cost/usage column is accurate.
    """
    prompt_total = await db.scalar(
        select(func.coalesce(func.sum(TranscriptEntry.prompt_tokens), 0)).where(
            TranscriptEntry.session_id == session_id
        )
    )
    completion_total = await db.scalar(
        select(func.coalesce(func.sum(TranscriptEntry.completion_tokens), 0)).where(
            TranscriptEntry.session_id == session_id
        )
    )
    return int(prompt_total or 0) + int(completion_total or 0)
