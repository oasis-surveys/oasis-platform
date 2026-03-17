"""
OASIS — Pipecat FrameProcessors that log transcript entries to PostgreSQL.

Two cooperating processors capture the full diarised transcript:

  TranscriptUserCapture  (placed BEFORE the context aggregator)
    Intercepts TranscriptionFrame from STT → logs user utterances.

  TranscriptLogger  (placed AFTER the LLM, before TTS)
    Intercepts TextFrame from LLM → buffers tokens and flushes full
    agent turns to the database.

Both share a single TranscriptLoggerState to keep sequence numbers
consistent and coordinate buffer flushing.

For Voice-to-Voice (V2V) pipelines where the Realtime LLM emits both
TranscriptionFrame and TextFrame downstream, both processors should be
placed after the LLM.

Everything is flushed to the DB asynchronously to avoid blocking the pipeline.
"""

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


class TranscriptLoggerState:
    """
    Shared mutable state for a pair of transcript processors.

    Holds the sequence counter, agent text buffer, and database / notification
    plumbing so both processors stay in sync.
    """

    def __init__(
        self,
        session_id: uuid.UUID,
        db_session_factory,
        *,
        notify_callback=None,
    ):
        self.session_id = session_id
        self.db_session_factory = db_session_factory
        self.notify_callback = notify_callback
        self.sequence: int = 0
        self.agent_buffer: list[str] = []

    async def persist_entry(self, role: str, content: str):
        """Write a single transcript entry to the DB."""
        from app.models.session import TranscriptEntry, SpeakerRole

        if not content.strip():
            return

        self.sequence += 1
        entry = TranscriptEntry(
            id=uuid.uuid4(),
            session_id=self.session_id,
            role=SpeakerRole(role),
            content=content.strip(),
            sequence=self.sequence,
            spoken_at=datetime.now(timezone.utc),
        )

        try:
            async with self.db_session_factory() as db:
                db.add(entry)
                await db.commit()
        except Exception as exc:
            logger.error(f"TranscriptLogger: failed to persist entry: {exc}")

        # Fire real-time notification
        if self.notify_callback:
            try:
                await self.notify_callback(
                    {
                        "type": "transcript",
                        "role": role,
                        "content": content.strip(),
                        "sequence": self.sequence,
                    }
                )
            except Exception:
                pass

    async def flush_agent_buffer(self):
        """Persist the accumulated agent turn."""
        if self.agent_buffer:
            full_text = "".join(self.agent_buffer)
            self.agent_buffer.clear()
            await self.persist_entry("agent", full_text)


class TranscriptUserCapture(FrameProcessor):
    """
    Captures user TranscriptionFrame and logs it to the database.

    Place BEFORE the LLM context aggregator in the modular pipeline so
    user speech is captured before it's consumed by the aggregator.

    For V2V pipelines, place after the Realtime LLM (it emits
    TranscriptionFrame downstream).
    """

    def __init__(self, state: TranscriptLoggerState, **kwargs):
        super().__init__(**kwargs)
        self._state = state

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, InterimTranscriptionFrame):
            # Partial transcription — pass through, don't log
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame):
            # Final user transcription → flush any pending agent text first
            await self._state.flush_agent_buffer()
            await self._state.persist_entry("user", frame.text)
            await self.push_frame(frame, direction)
            return

        # Everything else → pass through
        await self.push_frame(frame, direction)


class TranscriptLogger(FrameProcessor):
    """
    Buffers LLM-generated TextFrame tokens and flushes full agent turns.

    Place AFTER the LLM and BEFORE TTS in the modular pipeline.
    Agent text is flushed when:
      - a new user transcription triggers flush via the shared state
      - the pipeline ends (cleanup)
    """

    def __init__(self, state: TranscriptLoggerState, **kwargs):
        super().__init__(**kwargs)
        self._state = state

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TextFrame):
            # LLM-generated text (streamed token-by-token) — buffer it
            self._state.agent_buffer.append(frame.text)
            await self.push_frame(frame, direction)
            return

        # Everything else → pass through
        await self.push_frame(frame, direction)

    async def cleanup(self):
        """Flush remaining agent text on shutdown."""
        await self._state.flush_agent_buffer()
        await super().cleanup()
