"""
Structured Interview Guide — System-prompt-based approach.

Instead of a complex stateful processor, we construct a detailed system
prompt that tells the LLM exactly how to conduct the structured interview.

Modern LLMs (GPT-4o, GPT-5, Gemini 2.x) follow structured protocols
remarkably well.  We layer a lightweight turn-counter on top that nudges
the model if it lingers too long on one question.

Architecture
------------
1.  `build_structured_prompt()`  – creates the full system prompt from
    the researcher's guide + their base prompt.
2.  `InterviewGuideProcessor`   – a Pipecat FrameProcessor that sits in
    the pipeline and monitors agent/user turns.  After *max_follow_ups*
    exchanges on a question it injects an LLM system message to advance.
"""

from __future__ import annotations

import json
from typing import Optional

from loguru import logger
from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    Frame,
    LLMMessagesAppendFrame,
    StartFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


# ── Prompt builder ──────────────────────────────────────────────────────────

def build_structured_prompt(
    base_prompt: str,
    guide: dict,
) -> str:
    """
    Build a comprehensive system prompt that encodes the interview guide.

    Parameters
    ----------
    base_prompt : str
        The researcher's base system prompt (personality, context, etc.).
    guide : dict
        The interview_guide JSON from the Agent model.
        Expected shape:
        {
          "questions": [
            {
              "text": "...",
              "probes": ["...", "..."],
              "max_follow_ups": 3,
              "transition": "..."        # optional
            },
            ...
          ],
          "closing_message": "..."        # optional
        }

    Returns
    -------
    str
        Full system prompt with the interview protocol embedded.
    """
    questions = guide.get("questions", [])
    closing = guide.get(
        "closing_message",
        "Thank you for your time. This concludes our interview.",
    )

    if not questions:
        return base_prompt

    # Build the question guide section. We describe each question with a
    # canonical paraphrase, an explicit ordered probe list, and a hard cap
    # on follow-ups. The model is instructed to pick probes IN ORDER from
    # the list and NEVER reuse one — this stops the "could you tell me
    # about your background... could you tell me about your background..."
    # repetition we saw in production logs.
    guide_lines = []
    for i, q in enumerate(questions, 1):
        text = q.get("text", "")
        probes = q.get("probes", [])
        max_fu = q.get("max_follow_ups", 2)
        transition = q.get("transition", "")

        guide_lines.append(f"### Question {i} of {len(questions)}")
        guide_lines.append(f"Main question: {text}")
        if probes:
            guide_lines.append(
                f"Follow-up probes (use these in order, pick a different "
                f"one each time, do NOT invent your own):"
            )
            for j, p in enumerate(probes, 1):
                guide_lines.append(f"  {j}. {p}")
        guide_lines.append(
            f"Maximum follow-ups for this question: {max_fu}. "
            f"After {max_fu} follow-up(s) you MUST move on to the next "
            f"question, even if the answers were short."
        )
        if transition:
            guide_lines.append(f"Transition phrase to next question: {transition}")
        guide_lines.append("")

    question_guide = "\n".join(guide_lines)

    structured_section = f"""

---

## INTERVIEW PROTOCOL

You are conducting a structured interview. There are {len(questions)} questions
and you must ask them all, in the exact order below. The conversation must
follow this turn pattern:

  Q1 (main) → user → probe → user → probe → user → Q2 (main) → user → ...

Hard rules:
- NEVER ask the same question twice. Once you've asked the main question,
  do not ask it again, even rephrased — move to the probes.
- Ask probes verbatim from the list, picking a different one each turn.
  Do NOT invent your own probes.
- Do NOT acknowledge or evaluate answers ("great", "interesting",
  "that's helpful"). A neutral "Mm-hm." or going straight to the next
  probe is correct. Validation biases the participant.
- Do NOT narrate ("let's move on", "now I'll ask a follow-up",
  "transitioning"). Just ask the next thing.
- When you reach the maximum follow-ups for a question, move on to the
  next main question, even if the participant's answers were brief.

{question_guide}

### Closing
After the final question's follow-ups are done, say exactly: "{closing}"

You will not see your own previous turns reliably, so before each turn,
look at the conversation history and figure out:
1. Which question number are we on (1..{len(questions)})?
2. How many follow-ups have I already asked on this question?
3. Therefore, what comes next: another probe, or move to the next main question?

If unsure, advance rather than repeat.
"""

    return base_prompt.rstrip() + structured_section


# ── Stateful nudge processor ────────────────────────────────────────────────

DEFAULT_MAX_FOLLOW_UPS = 3


class InterviewGuideProcessor(FrameProcessor):
    """Lightweight safety net for structured interviews.

    The structured prompt does the heavy lifting: it tells the LLM exactly
    which questions to ask and in what order. This processor is a backup that
    counts agent turns per question and, if the model lingers past the
    configured ``max_follow_ups``, injects a system message nudging it to
    advance to the next question (or to wrap up if we're at the end).

    It also exposes ``current_question_index`` so other components can read
    progress, and emits structured log lines for observability.

    The processor is intentionally conservative:
        - It never blocks frames; it just *appends* a system message when
          needed.
        - One initial agent ask + ``max_follow_ups`` follow-ups = the
          allowed budget per question. The nudge is fired on the next
          ``UserStoppedSpeakingFrame`` after the budget is exhausted, so the
          LLM sees the nudge while it's about to respond.
        - It pairs with the structured prompt; without that prompt the
          processor still works but the model may not know how to interpret
          the nudges.
    """

    def __init__(self, guide: dict, name: str = "InterviewGuideProcessor"):
        super().__init__(name=name)
        self._guide = guide or {}
        self._questions = list(self._guide.get("questions") or [])
        self._closing = self._guide.get(
            "closing_message",
            "Thank you for your time. This concludes our interview.",
        )
        self.current_question_index = 0
        self._bot_turns_on_question = 0
        self._nudge_pending = False
        self._closed = False
        # Bot turns that happen *before* the participant has spoken (the
        # spoken welcome message in particular) used to be counted against
        # question 1's follow-up budget, which made the agent advance after
        # the very first probe. We gate counting on having seen at least one
        # ``UserStoppedSpeakingFrame`` so the welcome is free.
        self._user_has_spoken = False

    # ── Public read-only helpers ────────────────────────────────────────

    @property
    def total_questions(self) -> int:
        return len(self._questions)

    @property
    def is_finished(self) -> bool:
        return self._closed or self.current_question_index >= len(self._questions)

    def _current_max_follow_ups(self) -> int:
        if self.current_question_index >= len(self._questions):
            return DEFAULT_MAX_FOLLOW_UPS
        q = self._questions[self.current_question_index]
        try:
            return int(q.get("max_follow_ups", DEFAULT_MAX_FOLLOW_UPS))
        except (TypeError, ValueError):
            return DEFAULT_MAX_FOLLOW_UPS

    def _build_advance_message(self) -> Optional[dict]:
        """Build the nudge message asking the LLM to move on."""
        next_idx = self.current_question_index + 1
        if next_idx >= len(self._questions):
            self._closed = True
            return {
                "role": "system",
                "content": (
                    "[Interview protocol] You have completed all the questions "
                    "in the guide. Acknowledge the participant's last answer "
                    "briefly, then deliver the closing message: "
                    f'"{self._closing}"'
                ),
            }

        current_q = self._questions[self.current_question_index]
        next_q = self._questions[next_idx]
        transition = (current_q.get("transition") or "").strip()
        next_text = next_q.get("text", "")

        transition_hint = (
            f' Use this transition if it fits: "{transition}".'
            if transition
            else ""
        )
        return {
            "role": "system",
            "content": (
                f"[Interview protocol] You have explored question "
                f"{self.current_question_index + 1} of "
                f"{len(self._questions)} sufficiently. Acknowledge the "
                f"participant's last answer in one short sentence, then move "
                f"on to question {next_idx + 1}: \"{next_text}\"."
                f"{transition_hint}"
            ),
        }

    # ── Frame handling ──────────────────────────────────────────────────

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            self.current_question_index = 0
            self._bot_turns_on_question = 0
            self._nudge_pending = False
            self._closed = False
            self._user_has_spoken = False

        # Count agent turns. Two gates so the budget tracks *probes* and
        # not every TTS event:
        #   1. The participant must have spoken at least once. This stops
        #      the spoken welcome from being charged against question 1.
        #   2. The participant must have spoken since the last counted bot
        #      turn. This stops silence prompts ("Take your time...") and
        #      any other TTSSpeakFrame the agent emits while waiting on
        #      the user from being charged as additional probes. Without
        #      this gate, two silence prompts could exhaust a question's
        #      whole follow-up budget without the model ever asking a real
        #      probe, which is what made the structured template feel
        #      "stuck on the same question".
        elif (
            isinstance(frame, BotStoppedSpeakingFrame)
            and not self._closed
            and self._user_has_spoken
        ):
            self._bot_turns_on_question += 1
            budget = 1 + self._current_max_follow_ups()
            logger.debug(
                "[guide] q={} agent_turn={}/{}",
                self.current_question_index + 1,
                self._bot_turns_on_question,
                budget,
            )
            # Lock the counter until the participant speaks again. The
            # next TTS event (silence prompt, repeated greeting, etc.)
            # won't be counted unless a real user turn happens first.
            self._user_has_spoken = False
            if self._bot_turns_on_question >= budget:
                self._nudge_pending = True

        # When the user finishes their reply and a nudge is pending, push a
        # system message before the LLM context aggregator triggers a run.
        elif isinstance(frame, UserStoppedSpeakingFrame):
            self._user_has_spoken = True
            if self._nudge_pending:
                msg = self._build_advance_message()
                if msg is not None:
                    logger.info(
                        "[guide] advancing from q={} -> q={}",
                        self.current_question_index + 1,
                        self.current_question_index + 2,
                    )
                    await self.push_frame(
                        LLMMessagesAppendFrame(messages=[msg], run_llm=False),
                        FrameDirection.DOWNSTREAM,
                    )
                    if not self._closed:
                        self.current_question_index += 1
                        self._bot_turns_on_question = 0
                self._nudge_pending = False

        await self.push_frame(frame, direction)

    # ── Test/inspection helper ─────────────────────────────────────────

    def snapshot(self) -> dict:
        return {
            "current_question_index": self.current_question_index,
            "bot_turns_on_question": self._bot_turns_on_question,
            "nudge_pending": self._nudge_pending,
            "closed": self._closed,
            "total_questions": self.total_questions,
            "user_has_spoken": self._user_has_spoken,
        }


__all__ = [
    "build_structured_prompt",
    "InterviewGuideProcessor",
    "DEFAULT_MAX_FOLLOW_UPS",
]
