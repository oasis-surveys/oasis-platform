"""
Tests for the EngagementProcessor turn-boundary logic.

Regression coverage for two production bugs observed with segmented STT
(OpenAI Whisper emits one TranscriptionFrame per VAD segment):

1. A single spoken turn was scored once per fragment instead of once per
   turn, over-firing adaptive triggers mid-turn.
2. With a turn analyzer, UserStoppedSpeakingFrame arrives *after* the final
   fragment, so turns were only finalized at the start of the next turn —
   by which time the bot-stopped timestamp had been refreshed and the
   latency delta went negative, recording NULL for every turn.

Uses Pipecat's bundled ``run_test`` helper.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.tests.utils import SleepFrame, run_test

# UserStarted/StoppedSpeaking are system frames that overtake queued data
# frames; a short sleep between sends keeps the scripted ordering realistic.
_PACE = SleepFrame(sleep=0.05)

from app.engagement.adaptive import AdaptiveSignals
from app.pipeline.engagement_processor import EngagementProcessor


def _mock_db_factory():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, session


def _make_processor(signals=None):
    factory, db = _mock_db_factory()
    state = MagicMock()
    state.sequence = 7
    proc = EngagementProcessor(
        session_id=uuid.uuid4(),
        db_session_factory=factory,
        transcript_state=state,
        language="en",
        signals=signals,
    )
    return proc, db


async def _drain(proc):
    if proc._bg_tasks:
        await asyncio.gather(*list(proc._bg_tasks), return_exceptions=True)


def _tf(text):
    return TranscriptionFrame(text=text, user_id="u", timestamp="t")


class TestTurnAggregation:
    @pytest.mark.asyncio
    async def test_fragments_scored_once_per_turn_stop_after_last_fragment(self):
        """Observed production ordering: the aggregator broadcasts the stop
        after the final fragment's transcription has arrived."""
        signals = AdaptiveSignals()
        proc, db = _make_processor(signals)

        await run_test(
            processor=proc,
            frames_to_send=[
                BotStoppedSpeakingFrame(),
                _PACE,
                UserStartedSpeakingFrame(),
                _PACE,
                _tf("Yeah, uh..."),
                _tf("I'm a researcher and I really like"),
                _tf("playing basketball."),
                _PACE,
                UserStoppedSpeakingFrame(),
            ],
        )
        await _drain(proc)

        # One finalized turn covering all fragments.
        assert signals.turn_id == 1
        assert db.add.call_count >= 1
        turn_row = db.add.call_args_list[0][0][0]
        # "Yeah, uh..." (2) + "I'm a researcher and I really like" (7)
        # + "playing basketball." (2)
        assert turn_row.word_count == 11
        # Latency captured at user start (tiny but present in tests).
        assert turn_row.response_latency_ms is not None

    @pytest.mark.asyncio
    async def test_stop_before_only_fragment(self):
        """Single-segment turn: the VAD stop precedes the transcription (the
        STT needs the full segment audio) — the fragment completes the turn."""
        signals = AdaptiveSignals()
        proc, db = _make_processor(signals)

        await run_test(
            processor=proc,
            frames_to_send=[
                BotStoppedSpeakingFrame(),
                _PACE,
                UserStartedSpeakingFrame(),
                _PACE,
                UserStoppedSpeakingFrame(),
                _PACE,
                _tf("I work on statistics."),
            ],
        )
        await _drain(proc)

        assert signals.turn_id == 1
        turn_row = db.add.call_args_list[0][0][0]
        assert turn_row.word_count == 4

    @pytest.mark.asyncio
    async def test_late_fragment_mirrors_aggregator_clipping(self):
        """When the stop fires while a later segment's transcription is still
        in flight, Pipecat's aggregator runs the LLM with only the buffered
        fragments and treats the late one as a new mini-turn. The engagement
        record mirrors what the LLM consumed."""
        signals = AdaptiveSignals()
        proc, db = _make_processor(signals)

        await run_test(
            processor=proc,
            frames_to_send=[
                BotStoppedSpeakingFrame(),
                _PACE,
                UserStartedSpeakingFrame(),
                _PACE,
                _tf("I work on"),
                _PACE,
                UserStoppedSpeakingFrame(),
                _PACE,
                _tf("statistics."),  # late — becomes its own mini-turn
                _PACE,
                UserStartedSpeakingFrame(),  # aggregator's emulated turn start
                _PACE,
                UserStoppedSpeakingFrame(),
            ],
        )
        await _drain(proc)

        assert signals.turn_id == 2
        rows = [c[0][0] for c in db.add.call_args_list if hasattr(c[0][0], "word_count")]
        assert [r.word_count for r in rows] == [3, 1]

    @pytest.mark.asyncio
    async def test_two_turns_two_rows_with_latency(self):
        signals = AdaptiveSignals()
        proc, db = _make_processor(signals)

        await run_test(
            processor=proc,
            frames_to_send=[
                BotStoppedSpeakingFrame(),
                _PACE,
                UserStartedSpeakingFrame(),
                _PACE,
                _tf("First answer here."),
                _PACE,
                UserStoppedSpeakingFrame(),
                _PACE,
                BotStoppedSpeakingFrame(),
                _PACE,
                UserStartedSpeakingFrame(),
                _PACE,
                _tf("Second answer."),
                _PACE,
                UserStoppedSpeakingFrame(),
            ],
        )
        await _drain(proc)

        assert signals.turn_id == 2
        rows = [c[0][0] for c in db.add.call_args_list]
        turn_rows = [r for r in rows if hasattr(r, "word_count")]
        assert len(turn_rows) == 2
        assert all(r.response_latency_ms is not None for r in turn_rows)
        assert all(
            r.response_latency_ms >= 0 and r.response_latency_ms < 60_000
            for r in turn_rows
        )

    @pytest.mark.asyncio
    async def test_leftover_finalized_at_next_turn_start(self):
        """If no stop is seen (e.g. session glitch), the buffered turn is
        flushed when the next turn starts instead of being lost."""
        signals = AdaptiveSignals()
        proc, db = _make_processor(signals)

        await run_test(
            processor=proc,
            frames_to_send=[
                UserStartedSpeakingFrame(),
                _PACE,
                _tf("Orphaned answer."),
                _PACE,
                # No UserStoppedSpeakingFrame — next turn begins.
                UserStartedSpeakingFrame(),
                _PACE,
                _tf("Next answer."),
                _PACE,
                UserStoppedSpeakingFrame(),
            ],
        )
        await _drain(proc)

        assert signals.turn_id == 2
