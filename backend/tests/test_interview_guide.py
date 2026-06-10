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
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMMessagesAppendFrame,
    TextFrame,
    TranscriptionFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.tests.utils import SleepFrame, run_test

from app.pipeline.interview_guide import (
    DEFAULT_MAX_FOLLOW_UPS,
    InterviewGuideProcessor,
    StructuredOutputFilter,
    build_structured_prompt,
    looks_like_clarification,
)


# ── Helpers ────────────────────────────────────────────────────────────────


def _appended_messages(frames: List[Frame]) -> List[dict]:
    out: List[dict] = []
    for f in frames:
        if isinstance(f, LLMMessagesAppendFrame):
            out.extend(f.messages)
    return out


def _tf(text: str) -> TranscriptionFrame:
    return TranscriptionFrame(text=text, user_id="u", timestamp="t")


def _paced(*frames: Frame) -> List[Frame]:
    """Interleave a short sleep between frames. TranscriptionFrame is a
    queued DataFrame while the speaking frames are SystemFrames that jump
    the queue, so without pacing the test pushes them out of order — a race
    that doesn't exist in real sessions where frames arrive seconds apart."""
    out: List[Frame] = []
    for f in frames:
        out.append(f)
        out.append(SleepFrame(sleep=0.05))
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

    def test_closing_waits_for_final_answer(self, two_question_guide):
        out = build_structured_prompt("Hi.", two_question_guide)
        assert "the participant has given\ntheir final answer" in out
        assert "Never deliver the closing message in the same turn as a question" in out


def _llm_response(*chunks: str) -> List[Frame]:
    frames: List[Frame] = [LLMFullResponseStartFrame()]
    frames.extend(TextFrame(text=c) for c in chunks)
    frames.append(LLMFullResponseEndFrame())
    return frames


def _spoken_text(frames: List[Frame]) -> str:
    return "".join(f.text for f in frames if type(f) is TextFrame)


class TestStructuredOutputFilter:
    @pytest.mark.asyncio
    async def test_text_after_first_question_is_cut(self):
        """Regression replaying session 3bb8ac78: probe + leaked transition
        label + the NEXT main question, all crammed into one turn. Only the
        probe may reach the participant."""
        filt = StructuredOutputFilter()
        down, _ = await run_test(
            processor=filt,
            frames_to_send=_llm_response(
                "What was that experience like for you at the time?\n\n",
                "(Transition: Thanks, that's really helpful background.)\n\n",
                "Thinking about a specific recent moment, could you walk ",
                "me through what happened?",
            ),
        )
        spoken = _spoken_text(down)
        assert "What was that experience like for you at the time?" in spoken
        assert "Transition" not in spoken
        assert "helpful background" not in spoken
        assert "specific recent moment" not in spoken

    @pytest.mark.asyncio
    async def test_leading_transition_label_is_unwrapped(self):
        filt = StructuredOutputFilter()
        down, _ = await run_test(
            processor=filt,
            frames_to_send=_llm_response(
                "(Transition: Thanks, that's useful.) ",
                "Stepping back, what would have made a difference?",
            ),
        )
        spoken = _spoken_text(down)
        assert "Thanks, that's useful." in spoken
        assert "(Transition" not in spoken
        assert "Stepping back, what would have made a difference?" in spoken

    @pytest.mark.asyncio
    async def test_statement_only_turn_passes_through(self):
        filt = StructuredOutputFilter()
        down, _ = await run_test(
            processor=filt,
            frames_to_send=_llm_response(
                "Thank you for your time. ",
                "This concludes our interview.",
            ),
        )
        spoken = _spoken_text(down)
        assert "Thank you for your time." in spoken
        assert "This concludes our interview." in spoken

    @pytest.mark.asyncio
    async def test_preamble_before_question_is_kept(self):
        """A clarification answer followed by the repeated question is a
        legitimate turn shape — nothing before the first question may be
        dropped, and the cut starts only after it."""
        filt = StructuredOutputFilter()
        down, _ = await run_test(
            processor=filt,
            frames_to_send=_llm_response(
                "I mean a specific instance from your own life. ",
                "Could you share one? ",
                "Also, what first got you started?",
            ),
        )
        spoken = _spoken_text(down)
        assert "I mean a specific instance from your own life." in spoken
        assert "Could you share one?" in spoken
        assert "what first got you started" not in spoken

    @pytest.mark.asyncio
    async def test_chunks_split_mid_sentence(self):
        """Streamed tokens rarely align with sentence boundaries."""
        filt = StructuredOutputFilter()
        down, _ = await run_test(
            processor=filt,
            frames_to_send=_llm_response(
                "What were you thi", "nking or feeling at that point",
                "? Stepping ba", "ck, what would help?",
            ),
        )
        spoken = _spoken_text(down)
        assert "What were you thinking or feeling at that point?" in spoken
        assert "Stepping back" not in spoken

    @pytest.mark.asyncio
    async def test_consecutive_responses_reset_state(self):
        filt = StructuredOutputFilter()
        frames = _llm_response(
            "First question? This trailing text is cut.",
        ) + _llm_response(
            "Second turn statement. Second question?",
        )
        down, _ = await run_test(processor=filt, frames_to_send=frames)
        spoken = _spoken_text(down)
        assert "First question?" in spoken
        assert "trailing text" not in spoken
        assert "Second turn statement." in spoken
        assert "Second question?" in spoken


class TestLooksLikeClarification:
    @pytest.mark.parametrize(
        "text",
        [
            "What do you mean by a concrete example?",
            "Sorry, I didn't get the whole question.",
            "Sorry.",
            "Could you repeat that?",
            "At what point do you mean?",
            "Pardon?",
            "I don't understand the question.",
        ],
    )
    def test_english_clarifications_detected(self, text):
        assert looks_like_clarification(text) is True

    @pytest.mark.parametrize(
        ("language", "text"),
        [
            ("de", "Wie meinst du das genau in diesem Zusammenhang bitte"),
            ("de", "Das habe ich leider akustisch nicht verstanden gerade eben"),
            ("de", "Kannst du die ganze Frage bitte noch einmal wiederholen"),
            ("es", "Perdona, no entendí bien lo que me estabas preguntando ahí"),
            ("es", "¿Puedes repetir la pregunta una vez más por favor entonces?"),
            ("fr", "Désolé, je n'ai pas compris ce que vous venez de demander là"),
            ("fr", "Pouvez-vous répéter la question s'il vous plaît encore une fois"),
            ("pt", "Desculpa, não entendi direito o que você estava perguntando agora"),
            ("nl", "Wat bedoel je daar precies mee in deze context dan"),
            ("it", "Scusa, non ho capito bene cosa mi stavi chiedendo adesso"),
            ("zh", "不好意思，我没听清楚你刚才问的那个问题是什么内容"),
            ("ja", "すみません、今の質問がよく聞き取れませんでしたのでお願いします"),
            ("ko", "죄송한데 방금 하신 질문을 잘 못 들었어요 한번만 더요"),
            ("ar", "عذرا لم أفهم السؤال الذي طرحته للتو بشكل واضح"),
            ("hi", "माफ़ कीजिए, मुझे आपका सवाल ठीक से समझ नहीं आया अभी"),
            # English baseline always applies, regardless of agent language.
            ("de", "Sorry, I didn't get the whole question at all there"),
            # Region suffixes are ignored.
            ("de-DE", "Das habe ich leider gar nicht verstanden gerade"),
        ],
    )
    def test_localized_clarifications_detected(self, language, text):
        assert looks_like_clarification(text, language) is True

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "I really like soccer and I do research.",
            "I kind of started analyzing data to figure out the best team.",
            # Long answers ending in "?" are not clarifications.
            "I spent years collecting match data, building models, and "
            "comparing predictions to actual outcomes — does that count as "
            "a concrete example of what I find exciting about it?",
        ],
    )
    def test_answers_not_flagged(self, text):
        assert looks_like_clarification(text) is False

    def test_other_language_patterns_not_active_in_english(self):
        # A German answer mentioning "wiederholen" descriptively should not
        # trip the detector when the agent is configured for English… but
        # for a German agent it should.
        text = "Ich würde das Experiment gerne wiederholen"
        assert looks_like_clarification(text, "en") is False
        assert looks_like_clarification(text, "de") is True


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
        # Marked user-role note — mid-conversation system messages are
        # rejected by some chat APIs (OpenAI gpt-5.x).
        assert msgs[0]["role"] == "user"
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

    @pytest.mark.asyncio
    async def test_clarification_reply_does_not_burn_budget(
        self, two_question_guide
    ):
        """Regression: the agent's answer to "what do you mean?" was counted
        as a probe, so clarification exchanges exhausted the follow-up budget
        and forced an early advance."""
        proc = InterviewGuideProcessor(two_question_guide)
        frames_to_send = _paced(
            _tf("I work in research."),
            UserStoppedSpeakingFrame(),
            BotStoppedSpeakingFrame(),  # turn 1 (real probe)
            _tf("What do you mean by a concrete example?"),
            UserStoppedSpeakingFrame(),
            BotStoppedSpeakingFrame(),  # clarification answer — NOT counted
            _tf("Sorry, I didn't get the whole question."),
            UserStoppedSpeakingFrame(),
            BotStoppedSpeakingFrame(),  # repeat — NOT counted
        )
        down, _ = await run_test(
            processor=proc,
            frames_to_send=frames_to_send,
        )
        assert _appended_messages(down) == []
        assert proc.current_question_index == 0
        assert proc.snapshot()["bot_turns_on_question"] == 1

    @pytest.mark.asyncio
    async def test_closing_nudge_held_while_participant_asks_to_repeat(
        self, two_question_guide
    ):
        """Regression: at the final question, a "sorry, I didn't get that"
        triggered the close — the agent repeated the question and delivered
        the closing message in the same turn, never waiting for the answer.
        The nudge must be held until a substantive user turn."""
        proc = InterviewGuideProcessor(two_question_guide)
        frames_to_send = _paced(
            _tf("Hello."),
            UserStoppedSpeakingFrame(),
            # Exhaust Q1 budget (3 counted bot turns)
            BotStoppedSpeakingFrame(),
            _tf("I like soccer."),
            UserStoppedSpeakingFrame(),
            BotStoppedSpeakingFrame(),
            _tf("I analyze match statistics."),
            UserStoppedSpeakingFrame(),
            BotStoppedSpeakingFrame(),
            _tf("Mostly on weekends."),
            UserStoppedSpeakingFrame(),  # advance Q1 → Q2
            # Q2 budget = 1 + 1 = 2 counted bot turns
            BotStoppedSpeakingFrame(),
            _tf("Data quality is my pain point."),
            UserStoppedSpeakingFrame(),
            BotStoppedSpeakingFrame(),
            # Participant didn't catch the last question — must NOT close.
            _tf("Sorry, I didn't get the whole question."),
            UserStoppedSpeakingFrame(),
            BotStoppedSpeakingFrame(),  # agent repeats — uncounted
            # Now the real answer arrives — close fires here.
            _tf("Cleaning the raw data takes most of my time."),
            UserStoppedSpeakingFrame(),
        )
        down, _ = await run_test(
            processor=proc,
            frames_to_send=frames_to_send,
        )
        msgs = _appended_messages(down)
        assert len(msgs) == 2, f"expected advance + close, got {msgs}"
        closing = msgs[1]["content"]
        assert "completed all the questions" in closing
        assert "Thanks for your time." in closing
        assert "never combine a question with the closing message" in closing
        assert proc.is_finished is True

    def test_one_question_per_turn_rules_present(self, two_question_guide):
        out = build_structured_prompt("Hi.", two_question_guide)
        assert "at most ONE question mark" in out
        assert 'Never\n  read labels like "Transition:" aloud' in out

    def test_snapshot_mutates_with_state(self, two_question_guide):
        proc = InterviewGuideProcessor(two_question_guide)
        proc.current_question_index = 1
        proc._bot_turns_on_question = 2  # type: ignore[attr-defined]
        snap = proc.snapshot()
        assert snap["current_question_index"] == 1
        assert snap["bot_turns_on_question"] == 2
        assert snap["total_questions"] == 2
