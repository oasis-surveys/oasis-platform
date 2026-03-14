"""
SURVEYOR — Pipecat FrameProcessor that logs transcript entries to PostgreSQL.

Sits inside the pipeline and intercepts:
- TranscriptionFrame  → user utterances  (from STT)
- TextFrame / LLMTextFrame → agent tokens (from LLM, assembled into full turns)

Everything is flushed to the DB asynchronously to avoid blocking the pipeline.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from pipecat.frames.frames import (
    Frame,
    TranscriptionFrame,
    InterimTranscriptionFrame,
    TextFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class TranscriptLogger(FrameProcessor):
    """
    Intercepts transcription and LLM text frames to build a diarized transcript.

    Rather than writing to the DB on every single LLM token, we buffer agent
    text and flush the complete turn when:
      - a new user transcription arrives (next turn)
      - the pipeline ends (stop/cancel)
    """

    def __init__(
        self,
        session_id: uuid.UUID,
        db_session_factory,
        *,
        notify_callback=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._session_id = session_id
        self._db_session_factory = db_session_factory
        self._notify_callback = notify_callback  # for real-time WS push

        self._sequence = 0
        self._agent_buffer: list[str] = []

    # ── helpers ──────────────────────────────────────────────────

    async def _persist_entry(self, role: str, content: str):
        """Write a single transcript entry to the DB."""
        from app.models.session import TranscriptEntry, SpeakerRole

        if not content.strip():
            return

        self._sequence += 1
        entry = TranscriptEntry(
            id=uuid.uuid4(),
            session_id=self._session_id,
            role=SpeakerRole(role),
            content=content.strip(),
            sequence=self._sequence,
            spoken_at=datetime.now(timezone.utc),
        )

        try:
            async with self._db_session_factory() as db:
                db.add(entry)
                await db.commit()
        except Exception as exc:
            logger.error(f"TranscriptLogger: failed to persist entry: {exc}")

        # Fire real-time notification
        if self._notify_callback:
            try:
                await self._notify_callback(
                    {
                        "type": "transcript",
                        "role": role,
                        "content": content.strip(),
                        "sequence": self._sequence,
                    }
                )
            except Exception:
                pass

    async def _flush_agent_buffer(self):
        """Persist the accumulated agent turn."""
        if self._agent_buffer:
            full_text = "".join(self._agent_buffer)
            self._agent_buffer.clear()
            await self._persist_entry("agent", full_text)

    # ── frame processing ─────────────────────────────────────────

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, InterimTranscriptionFrame):
            # Partial transcription — pass through, don't log
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame):
            # Final user transcription → flush any pending agent text first
            await self._flush_agent_buffer()
            await self._persist_entry("user", frame.text)
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TextFrame):
            # LLM-generated text (streamed token-by-token) — buffer it
            self._agent_buffer.append(frame.text)
            await self.push_frame(frame, direction)
            return

        # Everything else → pass through
        await self.push_frame(frame, direction)

    async def cleanup(self):
        """Flush remaining agent text on shutdown."""
        await self._flush_agent_buffer()
        await super().cleanup()
