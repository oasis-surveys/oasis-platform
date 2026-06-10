"""
OASIS — Adaptive behavior processor (Phase 3a, modular voice pipeline).

Reads the per-turn engagement signals written by ``EngagementProcessor`` and,
when the agent has an adaptive policy, takes at most one prompt action and one
pace action per turn. In ``shadow`` mode nothing is applied; actions are only
recorded. Every action (applied or shadow) is persisted for disclosure.

Placement: immediately after ``EngagementProcessor`` and before the user
context aggregator, so an injected system message lands before the next LLM
turn (the same mechanism ``InterviewGuideProcessor`` uses).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Optional

from loguru import logger

from pipecat.frames.frames import (
    Frame,
    LLMMessagesAppendFrame,
    TranscriptionFrame,
    TTSUpdateSettingsFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from app.engagement.adaptive import (
    PROMPT,
    TTS_SPEED,
    AdaptivePolicy,
    AdaptivePolicyEngine,
    AdaptiveSignals,
    guidance_message,
)

# TTS providers whose Pipecat service accepts a runtime ``speed`` setting.
_SPEED_PROVIDERS = {"elevenlabs", "openai", "cartesia", "self_hosted"}


def supports_tts_speed(provider: Optional[str]) -> bool:
    return (provider or "").lower() in _SPEED_PROVIDERS


class AdaptiveBehaviorProcessor(FrameProcessor):
    def __init__(
        self,
        *,
        session_id: uuid.UUID,
        db_session_factory,
        signals: AdaptiveSignals,
        policy: AdaptivePolicy,
        tts_provider: Optional[str] = None,
        name: str = "AdaptiveBehaviorProcessor",
    ):
        super().__init__(name=name)
        self._session_id = session_id
        self._db_session_factory = db_session_factory
        self._signals = signals
        self._engine = AdaptivePolicyEngine(policy)
        self._tts_provider = tts_provider
        self._current_speed = 1.0
        self._last_turn_id = 0
        self._bg_tasks: set[asyncio.Task] = set()

    def _spawn(self, coro) -> None:
        """Run audit persistence off the frame's critical path."""
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        to_record: list[tuple] = []
        # Act only when the engagement processor has finalized a new complete
        # turn; intermediate STT fragments pass through untouched.
        if (
            isinstance(frame, TranscriptionFrame)
            and self._signals.turn_id != self._last_turn_id
        ):
            self._last_turn_id = self._signals.turn_id
            try:
                to_record = await self._maybe_adapt()
            except Exception as exc:  # never break the pipeline
                logger.error(f"AdaptiveBehaviorProcessor error: {exc}")
        await self.push_frame(frame, direction)

        # Audit rows are written off the critical path; the injected frames
        # above are what must precede the upcoming turn, not the DB write.
        for act, sequence, applied in to_record:
            self._spawn(self._record(act, sequence, applied))

    async def _maybe_adapt(self) -> list[tuple]:
        triggers = self._signals.triggers()
        if not triggers:
            return []
        actions = self._engine.evaluate(triggers, time.monotonic())
        if not actions:
            return []

        live = self._engine.policy.is_live
        sequence = self._signals.transcript_sequence
        to_record: list[tuple] = []

        for act in actions:
            applied = False
            if live:
                if act.type == PROMPT and act.instruction:
                    # Injected as a marked user-role note: several chat APIs
                    # (OpenAI gpt-5.x among them) reject a system message that
                    # appears after an assistant message with a 400.
                    await self.push_frame(
                        LLMMessagesAppendFrame(
                            messages=[guidance_message(act.instruction)],
                            run_llm=False,
                        ),
                        FrameDirection.DOWNSTREAM,
                    )
                    applied = True
                elif act.type == TTS_SPEED and supports_tts_speed(self._tts_provider):
                    speed = float(act.params.get("speed", 1.0))
                    if abs(speed - self._current_speed) > 1e-6:
                        await self.push_frame(
                            TTSUpdateSettingsFrame(settings={"speed": speed}),
                            FrameDirection.DOWNSTREAM,
                        )
                        self._current_speed = speed
                        applied = True

            to_record.append((act, sequence, applied))

        return to_record

    async def _record(self, act, sequence: int, applied: bool) -> None:
        from app.models.engagement import AdaptiveAction

        detail: dict = {"applied": applied}
        if act.type == PROMPT:
            detail["instruction"] = act.instruction
        else:
            detail["params"] = act.params
            if act.type == TTS_SPEED and not supports_tts_speed(self._tts_provider):
                detail["note"] = "tts_provider_does_not_support_speed"

        try:
            async with self._db_session_factory() as db:
                db.add(
                    AdaptiveAction(
                        id=uuid.uuid4(),
                        session_id=self._session_id,
                        transcript_sequence=sequence,
                        trigger=act.trigger,
                        action=act.action,
                        mode=self._engine.policy.mode,
                        detail=detail,
                    )
                )
                await db.commit()
        except Exception as exc:
            logger.error(f"AdaptiveBehaviorProcessor: failed to record action: {exc}")
