"""
OASIS — EngagementTurn model.

One row per participant turn in a voice interview when the agent has
engagement tracking enabled. Holds raw per-turn features plus a derived
score/label. Append-only; computed observationally and never alters the
interview itself (Phase 1).
"""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class EngagementTurn(Base):
    __tablename__ = "engagement_turns"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Links to the matching user TranscriptEntry.sequence.
    transcript_sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Raw features ──
    response_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    voiced_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    speech_rate_wpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    filler_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rms_energy: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Derived ──
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    label: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Room for signals not yet promoted to columns (per-turn flags, etc.).
    extras: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    session = relationship("Session", back_populates="engagement_turns")


class EngagementEvent(Base):
    """A discrete rolling-window engagement event for a session (Phase 2)."""

    __tablename__ = "engagement_events"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The turn that triggered the event, if applicable.
    transcript_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    score_at_event: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    session = relationship("Session", back_populates="engagement_events")


class AdaptiveAction(Base):
    """A record of an adaptive behavior action (Phase 3, audit/disclosure).

    Written whether the action was applied (``mode='live'``) or only logged
    (``mode='shadow'``), so researchers can see exactly what adaptation did or
    would have done.
    """

    __tablename__ = "adaptive_actions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    transcript_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trigger: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    session = relationship("Session", back_populates="adaptive_actions")
