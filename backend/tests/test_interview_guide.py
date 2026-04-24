"""
Tests for the structured-interview InterviewGuideProcessor.

We use Pipecat's bundled ``run_test`` helper to spin up a 3-processor pipeline
(source → InterviewGuideProcessor → sink), feed it scripted frames, and
inspect the downstream output.
"""

from __future__ import annotations

from typing import List

import pytest

from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    Frame,
    LLMMessagesAppendFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.tests.utils import run_test

from app.pipeline.interview_guide import (
    DEFAULT_MAX_FOLLOW_UPS,
    InterviewGuideProcessor,
    build_structured_prompt,
)


# ── Helpers ────────────────────────────────────────────────────────────────


def _appended_messages(frames: List[Frame]) -> List[dict]:
    out: List[dict] = []
    for f in frames:
        if isinstance(f, LLMMessagesAppendFrame):
            out.extend(f.messages)
    return out


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def two_question_guide() -> dict:
    return {
        "questions": [
            {
                "text": "Tell me about your typical day.",
                "probes": ["Walk me through this morning."],
                "max_follow_ups": 2,
                "transition": "Great, let's switch gears.",
            },
            {
                "text": "What's your biggest pain point right now?",
                "probes": ["Why is that the most important?"],
                "max_follow_ups": 1,
            },
        ],
        "closing_message": "Thanks for your time.",
    }


# ── build_structured_prompt sanity ──────────────────────────────────────────


class TestBuildStructuredPrompt:
    def test_prompt_includes_each_question(self, two_question_guide):
        out = build_structured_prompt("Be friendly.", two_question_guide)
        assert "Be friendly." in out
        assert "Tell me about your typical day." in out
        assert "What's your biggest pain point right now?" in out
        assert "INTERVIEW PROTOCOL" in out
        assert "Thanks for your time." in out

    def test_empty_guide_returns_base_prompt_unchanged(self):
        out = build_structured_prompt("Be friendly.", {"questions": []})
        assert out == "Be friendly."

    def test_default_closing_when_omitted(self):
        out = build_structured_prompt(
            "Hi.",
            {"questions": [{"text": "Q?", "probes": [], "max_follow_ups": 1}]},
        )
        assert "concludes our interview" in out

    def test_anti_repeat_and_neutrality_rules_present(self, two_question_guide):
        """Regression: production logs showed the model repeating Q1 and
        validating answers ('great', 'interesting'). The protocol must
        explicitly forbid both."""
        out = build_structured_prompt("Hi.", two_question_guide)
        assert "NEVER ask the same question twice" in out
        assert "great" in out  # part of the don't-validate rule
        assert "Do NOT acknowledge or evaluate" in out

    def test_probe_list_is_ordered_and_marked_verbatim(self, two_question_guide):
        out = build_structured_prompt("Hi.", two_question_guide)
        # Probes must be numbered and the prompt must say to use them
        # verbatim rather than invent new ones.
        assert "use these in order" in out
        assert "do NOT invent your own" in out
        assert "1. Walk me through this morning." in out

    def test_max_followups_is_a_hard_cap(self, two_question_guide):
        out = build_structured_prompt("Hi.", two_question_guide)
        assert "Maximum follow-ups for this question: 2" in out
        assert "you MUST move on to the next" in out


# ── InterviewGuideProcessor state machine ──────────────────────────────────


class TestInterviewGuideProcessor:
    def test_initial_state(self, two_question_guide):
        proc = InterviewGuideProcessor(two_question_guide)
        snap = proc.snapshot()
        assert snap["current_question_index"] == 0
        assert snap["bot_turns_on_question"] == 0
        assert snap["nudge_pending"] is False
        assert snap["closed"] is False
        assert snap["total_questions"] == 2
        assert snap["user_has_spoken"] is False

    @pytest.mark.asyncio
    async def test_no_nudge_within_budget(self, two_question_guide):
        proc = InterviewGuideProcessor(two_question_guide)
        # Q1 has max_follow_ups=2, so budget is 1 initial + 2 follow-ups = 3 bot turns.
        # We start with the spoken welcome (BotStopped), then the first user reply
        # opens the budget window. 2 counted bot turns is well under budget.
        frames_to_send = [
            BotStoppedSpeakingFrame(),  # welcome — NOT counted
            UserStoppedSpeakingFrame(),  # user has now spoken
            BotStoppedSpeakingFrame(),  # turn 1
            UserStoppedSpeakingFrame(),
            BotStoppedSpeakingFrame(),  # turn 2
            UserStoppedSpeakingFrame(),
        ]
        down, _ = await run_test(
            processor=proc,
            frames_to_send=frames_to_send,
            expected_down_frames=[
                BotStoppedSpeakingFrame,
                UserStoppedSpeakingFrame,
                BotStoppedSpeakingFrame,
                UserStoppedSpeakingFrame,
                BotStoppedSpeakingFrame,
                UserStoppedSpeakingFrame,
            ],
        )
        assert _appended_messages(down) == []
        assert proc.current_question_index == 0

    @pytest.mark.asyncio
    async def test_welcome_message_does_not_count_against_budget(
        self, two_question_guide
    ):
        """Bot turns before the participant speaks (the spoken welcome) must
        not eat into question 1's follow-up budget."""
        proc = InterviewGuideProcessor(two_question_guide)
        # 3 bot turns BEFORE any user turn — historically this would have
        # exhausted Q1 (budget = 3). After the fix, none of these count.
        frames_to_send = [
            BotStoppedSpeakingFrame(),
            BotStoppedSpeakingFrame(),
            BotStoppedSpeakingFrame(),
            UserStoppedSpeakingFrame(),
        ]
        down, _ = await run_test(
            processor=proc,
            frames_to_send=frames_to_send,
        )
        assert _appended_messages(down) == []
        assert proc.current_question_index == 0

    @pytest.mark.asyncio
    async def test_nudge_fires_after_budget_exhausted(self, two_question_guide):
        proc = InterviewGuideProcessor(two_question_guide)
        # The processor only counts ONE bot turn per intervening user turn,
        # so we have to alternate User/Bot to spend the budget. Q1 budget =
        # 1 + max_follow_ups=2 = 3 bot turns.
        frames_to_send = [
            UserStoppedSpeakingFrame(),  # user opens conversation
            BotStoppedSpeakingFrame(),  # ask Q1 (turn 1)
            UserStoppedSpeakingFrame(),
            BotStoppedSpeakingFrame(),  # probe (turn 2)
            UserStoppedSpeakingFrame(),
            BotStoppedSpeakingFrame(),  # probe (turn 3) -> budget hit
            UserStoppedSpeakingFrame(),  # nudge fires here
        ]
        down, _ = await run_test(
            processor=proc,
            frames_to_send=frames_to_send,
        )
        msgs = _appended_messages(down)
        assert len(msgs) == 1, f"expected 1 nudge, got {msgs}"
        assert msgs[0]["role"] == "system"
        assert "question 2" in msgs[0]["content"]
        assert "biggest pain point" in msgs[0]["content"]
        assert "Great, let's switch gears." in msgs[0]["content"]
        assert proc.current_question_index == 1

    @pytest.mark.asyncio
    async def test_silence_prompt_does_not_count_as_probe(
        self, two_question_guide
    ):
        """Regression: silence prompts ('take your time') are TTSSpeakFrames
        that emit BotStoppedSpeakingFrame too. They must NOT count against
        the question budget, otherwise a couple of silence nudges would
        prematurely advance Q1 without the model ever asking a real probe.
        """
        proc = InterviewGuideProcessor(two_question_guide)
        frames_to_send = [
            UserStoppedSpeakingFrame(),  # user opens
            BotStoppedSpeakingFrame(),  # real bot ask -> turn 1
            # User goes quiet — simulate three silence prompts firing in a
            # row without any user turn in between. None should count.
            BotStoppedSpeakingFrame(),
            BotStoppedSpeakingFrame(),
            BotStoppedSpeakingFrame(),
            UserStoppedSpeakingFrame(),  # user finally responds
            BotStoppedSpeakingFrame(),  # real probe -> turn 2
            UserStoppedSpeakingFrame(),
        ]
        down, _ = await run_test(
            processor=proc,
            frames_to_send=frames_to_send,
        )
        # Budget = 3, only 2 real turns counted, no nudge.
        assert _appended_messages(down) == []
        assert proc.current_question_index == 0
        assert proc.snapshot()["bot_turns_on_question"] == 2

    @pytest.mark.asyncio
    async def test_closing_nudge_after_final_question(self, two_question_guide):
        proc = InterviewGuideProcessor(two_question_guide)
        frames_to_send = [
            UserStoppedSpeakingFrame(),
            # Exhaust Q1 budget (3 counted bot turns, alternating with user)
            BotStoppedSpeakingFrame(),
            UserStoppedSpeakingFrame(),
            BotStoppedSpeakingFrame(),
            UserStoppedSpeakingFrame(),
            BotStoppedSpeakingFrame(),
            UserStoppedSpeakingFrame(),  # advance Q1 → Q2
            # Q2 budget = 1 + 1 = 2 counted bot turns
            BotStoppedSpeakingFrame(),
            UserStoppedSpeakingFrame(),
            BotStoppedSpeakingFrame(),
            UserStoppedSpeakingFrame(),  # closing nudge
        ]
        down, _ = await run_test(
            processor=proc,
            frames_to_send=frames_to_send,
        )
        msgs = _appended_messages(down)
        assert len(msgs) == 2, f"expected 2 nudges, got {len(msgs)}: {msgs}"
        closing = msgs[1]["content"]
        assert "completed all the questions" in closing
        assert "Thanks for your time." in closing
        assert proc.is_finished is True

    @pytest.mark.asyncio
    async def test_default_max_follow_ups_when_unset(self):
        guide = {
            "questions": [{"text": "Open?", "probes": []}],
            "closing_message": "Bye.",
        }
        proc = InterviewGuideProcessor(guide)
        # Budget = 1 + DEFAULT_MAX_FOLLOW_UPS counted bot turns. Alternate
        # so each one is actually counted.
        frames: List[Frame] = [UserStoppedSpeakingFrame()]
        for _ in range(1 + DEFAULT_MAX_FOLLOW_UPS):
            frames.append(BotStoppedSpeakingFrame())
            frames.append(UserStoppedSpeakingFrame())
        down, _ = await run_test(
            processor=proc,
            frames_to_send=frames,
        )
        msgs = _appended_messages(down)
        assert len(msgs) == 1
        assert "completed all the questions" in msgs[0]["content"]

    def test_snapshot_mutates_with_state(self, two_question_guide):
        proc = InterviewGuideProcessor(two_question_guide)
        proc.current_question_index = 1
        proc._bot_turns_on_question = 2  # type: ignore[attr-defined]
        snap = proc.snapshot()
        assert snap["current_question_index"] == 1
        assert snap["bot_turns_on_question"] == 2
        assert snap["total_questions"] == 2
