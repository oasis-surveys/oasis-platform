"""
OASIS — Engagement metrics processor (modular voice pipeline).

Observe-only FrameProcessor. It watches the frames already flowing through
the pipeline, computes per-turn participant features, scores them with the
rule-based scorer, and persists one row per turn. It never swallows,
reorders, or rewrites frames, and it never changes the interview.

Turn boundaries
---------------
Segmented STT services (OpenAI, Whisper) emit one ``TranscriptionFrame`` per
VAD speech segment, so a single spoken turn can produce several fragments
("Ja, so" / "I was just feeling" / "Very happy."). Scoring each fragment
would label every turn "very short answer" and over-fire events, so this
processor aggregates fragments and finalizes once per turn:

- ``UserStartedSpeakingFrame`` opens a turn (fires once per turn when a turn
  analyzer is active). Response latency is captured here, as the gap since
  the agent last stopped speaking.
- ``TranscriptionFrame`` fragments are buffered.
- The turn is finalized on whichever comes last: ``UserStoppedSpeakingFrame``
  (the aggregator's turn-stop broadcast, which with a turn analyzer fires
  after the final fragment's transcription has arrived) or, if the stop is
  seen first, the next ``TranscriptionFrame``. Any leftover is finalized when
  the next turn starts.

Placement: immediately after ``TranscriptUserCapture`` so the shared
transcript sequence is already assigned when a user turn finalizes.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Optional

from loguru import logger

from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    Frame,
    InputAudioRawFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from app.engagement.events import EventDetector
from app.engagement.features import TurnFeatures
from app.engagement.scorer import RuleBasedScorer, ScorerConfig

_MAX_TURN_PCM_BYTES = 16000 * 2 * 60  # ~60s of 16kHz mono int16, safety cap


class EngagementProcessor(FrameProcessor):
    def __init__(
        self,
        *,
        session_id: uuid.UUID,
        db_session_factory,
        transcript_state,
        language: Optional[str] = "en",
        notify_callback=None,
        config: Optional[dict] = None,
        signals=None,
        name: str = "EngagementProcessor",
    ):
        super().__init__(name=name)
        self._session_id = session_id
        self._db_session_factory = db_session_factory
        self._state = transcript_state
        self._language = language
        self._notify_callback = notify_callback
        self._signals = signals
        scorer_config = ScorerConfig.from_dict(config)
        self._scorer = RuleBasedScorer(scorer_config)
        self._detector = EventDetector(scorer_config)

        self._agent_stopped_at: Optional[float] = None
        self._user_started_at: Optional[float] = None
        self._user_stopped_at: Optional[float] = None
        self._pending_latency_ms: Optional[int] = None
        self._turn_stopped = False
        self._capturing = False
        self._pcm = bytearray()
        self._fragments: list[str] = []
        self._bg_tasks: set[asyncio.Task] = set()

    def _spawn(self, coro) -> None:
        """Run observational work off the frame's critical path."""
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        computed = None
        try:
            if isinstance(frame, BotStoppedSpeakingFrame):
                self._agent_stopped_at = time.monotonic()
            elif isinstance(frame, UserStartedSpeakingFrame):
                # Leftover from a turn that was never finalized.
                if self._fragments:
                    computed = self._finalize_turn()
                now = time.monotonic()
                self._user_started_at = now
                self._user_stopped_at = None
                # Capture latency at turn start; the bot-stopped timestamp is
                # consumed so a barge-in or silence prompt can't reuse it.
                if self._agent_stopped_at is not None and now >= self._agent_stopped_at:
                    self._pending_latency_ms = int((now - self._agent_stopped_at) * 1000.0)
                else:
                    self._pending_latency_ms = None
                self._agent_stopped_at = None
                self._turn_stopped = False
                self._capturing = True
                self._pcm.clear()
                self._fragments.clear()
            elif isinstance(frame, UserStoppedSpeakingFrame):
                self._user_stopped_at = time.monotonic()
                self._turn_stopped = True
                self._capturing = False
                # With a turn analyzer the aggregator broadcasts the stop only
                # after the final fragment's transcription arrived, so this is
                # normally where the turn completes.
                if self._fragments:
                    computed = self._finalize_turn()
            elif isinstance(frame, InputAudioRawFrame):
                if self._capturing and len(self._pcm) < _MAX_TURN_PCM_BYTES:
                    if frame.audio:
                        self._pcm.extend(frame.audio)
            elif isinstance(frame, TranscriptionFrame):
                if frame.text and frame.text.strip():
                    self._fragments.append(frame.text.strip())
                # Stop seen before the final fragment (fast turn analyzer):
                # this fragment completes the turn.
                if self._turn_stopped and self._fragments:
                    computed = self._finalize_turn()
        except Exception as exc:  # never break the pipeline
            logger.error(f"EngagementProcessor error: {exc}")

        await self.push_frame(frame, direction)

        # Persistence and notifications are deferred so they never add latency
        # to the participant turn reaching the LLM.
        if computed is not None:
            features, result, events = computed
            self._spawn(self._persist_and_publish(features, result, events))

    def _voiced_ms(self) -> Optional[int]:
        if self._user_started_at is None or self._user_stopped_at is None:
            return None
        delta = (self._user_stopped_at - self._user_started_at) * 1000.0
        if delta < 0:
            return None
        return int(delta)

    def _finalize_turn(self):
        """Score the aggregated turn (in-memory only) and reset state."""
        sequence = getattr(self._state, "sequence", 0)
        text = " ".join(self._fragments)
        features = TurnFeatures.from_turn(
            transcript_sequence=sequence,
            text=text,
            language=self._language,
            response_latency_ms=self._pending_latency_ms,
            voiced_ms=self._voiced_ms(),
            pcm=bytes(self._pcm),
        )
        result = self._scorer.score(features)
        events = self._detector.observe(result.label)

        # Share this turn's result with the adaptive processor. Bumping
        # turn_id tells it a new, complete turn is ready to act on.
        if self._signals is not None:
            self._signals.transcript_sequence = features.transcript_sequence
            self._signals.score = result.score
            self._signals.label = result.label
            self._signals.events = [e.event_type for e in events]
            self._signals.flags = list(result.flags)
            self._signals.turn_id += 1

        # Reset per-turn capture state for the next turn.
        self._pcm.clear()
        self._fragments.clear()
        self._turn_stopped = False
        self._user_started_at = None
        self._user_stopped_at = None
        self._pending_latency_ms = None

        return features, result, events

    async def _persist_and_publish(self, features: TurnFeatures, result, events) -> None:
        await self._persist(features, result, events)
        await self._publish(features, result, events)

    async def _persist(self, features: TurnFeatures, result, events) -> None:
        from app.models.engagement import EngagementEvent, EngagementTurn

        row = EngagementTurn(
            id=uuid.uuid4(),
            session_id=self._session_id,
            transcript_sequence=features.transcript_sequence,
            response_latency_ms=features.response_latency_ms,
            voiced_ms=features.voiced_ms,
            word_count=features.word_count,
            char_count=features.char_count,
            speech_rate_wpm=features.speech_rate_wpm,
            filler_count=features.filler_count,
            rms_energy=features.rms_energy,
            score=result.score,
            label=result.label,
            extras={"flags": result.flags, "components": result.components},
        )
        try:
            async with self._db_session_factory() as db:
                db.add(row)
                for ev in events:
                    db.add(
                        EngagementEvent(
                            id=uuid.uuid4(),
                            session_id=self._session_id,
                            transcript_sequence=features.transcript_sequence,
                            event_type=ev.event_type,
                            score_at_event=result.score,
                            payload=ev.payload,
                        )
                    )
                await db.commit()
        except Exception as exc:
            logger.error(f"EngagementProcessor: failed to persist turn: {exc}")

    async def _publish(self, features: TurnFeatures, result, events) -> None:
        if not self._notify_callback:
            return
        try:
            await self._notify_callback(
                {
                    "type": "engagement",
                    "sequence": features.transcript_sequence,
                    "score": result.score,
                    "label": result.label,
                    "flags": result.flags,
                    "events": [ev.event_type for ev in events],
                }
            )
        except Exception:
            pass
