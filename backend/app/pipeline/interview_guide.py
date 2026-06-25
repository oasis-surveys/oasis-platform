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
import re
from functools import lru_cache
from typing import Optional

from loguru import logger
from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    Frame,
    InterimTranscriptionFrame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMMessagesAppendFrame,
    StartFrame,
    TextFrame,
    TranscriptionFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


# ── Clarification detection ─────────────────────────────────────────────────
#
# The hard turn-counter below is content-blind by default: it charges EVERY
# bot turn against the question's follow-up budget. In production that meant
# the agent's answers to "what do you mean?" / "sorry, I didn't get that" and
# its verbatim question repeats burned the budget, so the safety nudge fired
# while the participant had never actually answered — worst at the final
# question, where the agent repeated the question and delivered the closing
# message in the same breath.
#
# This heuristic flags user turns that are clarification/repeat requests so
# the bot's *reply* to them is not counted as a probe. Pattern sets exist for
# every language the agent form offers; detection follows the agent's
# configured ``language``. English patterns are always included as a baseline
# because participants commonly code-switch ("Sorry, das habe ich nicht
# verstanden"). For languages without a pattern set, only the English
# baseline and the generic short-question heuristic apply.

_CLARIFICATION_PATTERNS_BY_LANG: dict[str, list[str]] = {
    "en": [
        r"\bwhat do you mean\b",
        r"\bwhat does that mean\b",
        r"\bdidn'?t (get|hear|catch|understand)\b",
        r"\bdon'?t (understand|get it|follow)\b",
        r"\b(can|could) you (repeat|rephrase|clarify|explain)\b",
        r"\bsay (that|it) again\b",
        r"\bcome again\b",
        r"\bpardon\b",
        r"\bsorry\b",
        r"\bmissed (that|the question)\b",
        r"\bwhat was (that|the question)\b",
        r"\bnot sure what you('re| are) asking\b",
    ],
    "de": [
        r"\b(wie|was) (meinst du|meinen sie)\b",
        r"\bnicht verstanden\b",
        r"\bverstehe (das |die frage )?nicht\b",
        r"\bnicht mitbekommen\b",
        r"\bwiederholen\b",
        r"\bnoch ?mal\b",
        r"\bentschuldigung\b",
        r"\btut mir leid\b",
    ],
    "es": [
        r"\bqué (quieres|quiere) decir\b",
        r"\bno (entiendo|entendí)\b",
        r"\b(puedes|puede) repetir\b",
        r"\bperd(ón|ona|one)\b",
        r"\bdisculp[ae]\b",
        r"\bno (te |le |lo )?(escuché|oí)\b",
        r"\botra vez\b",
        r"\brepite\b",
    ],
    "fr": [
        r"\bqu'?est[- ]ce que (tu veux|vous voulez) dire\b",
        r"\bje ne comprends pas\b",
        r"\bje n'?ai pas compris\b",
        r"\b(peux-tu|pouvez-vous) (répéter|reformuler|clarifier)\b",
        r"\bpardon\b",
        r"\bdésolé\b",
        r"\bpas (entendu|compris)\b",
        r"\bencore une fois\b",
    ],
    "pt": [
        r"\bo que (você )?quer dizer\b",
        r"\bnão (entendi|entendo)\b",
        r"\bpode repetir\b",
        r"\bdesculp[ae]\b",
        r"\bperdão\b",
        r"\bnão ouvi\b",
        r"\bde novo\b",
        r"\brepetir\b",
    ],
    "nl": [
        r"\bwat bedoel(t u| je)\b",
        r"\b(ik )?begrijp (het|dat) niet\b",
        r"\bniet begrepen\b",
        r"\b(kun je|kunt u) (dat |het )?herhalen\b",
        r"\bsorry\b",
        r"\bpardon\b",
        r"\bniet verstaan\b",
        r"\bnog een keer\b",
    ],
    "it": [
        r"\bcosa (intendi|intende)\b",
        r"\bnon (capisco|ho capito)\b",
        r"\b(puoi|può) ripetere\b",
        r"\bscus[ai]\b",
        r"\bnon ho sentito\b",
        r"\bdi nuovo\b",
        r"\bripetere\b",
    ],
    # No word boundaries in CJK scripts — plain substring patterns.
    "zh": [
        r"什么意思",
        r"没听懂",
        r"没听清",
        r"听不懂",
        r"再说一遍",
        r"不明白",
        r"不好意思",
    ],
    "ja": [
        r"どういう意味",
        r"わかりません",
        r"分かりません",
        r"聞き取れません",
        r"聞こえません",
        r"もう一度",
        r"すみません",
    ],
    "ko": [
        r"무슨 뜻",
        r"이해가 안",
        r"못 들었",
        r"다시 말씀",
        r"다시 한번",
        r"죄송",
    ],
    "ar": [
        r"ماذا تقصد",
        r"لم أفهم",
        r"لا أفهم",
        r"أعد",
        r"كرر",
        r"عفوا",
        r"لم أسمع",
    ],
    "hi": [
        r"क्या मतलब",
        r"समझ नहीं",
        r"समझा नहीं",
        r"फिर से",
        r"दोबारा",
        r"सुनाई नहीं",
        r"माफ़",
    ],
}


@lru_cache(maxsize=None)
def _clarification_re(lang: str) -> re.Pattern:
    patterns = list(_CLARIFICATION_PATTERNS_BY_LANG["en"])
    if lang != "en":
        patterns += _CLARIFICATION_PATTERNS_BY_LANG.get(lang, [])
    return re.compile("|".join(patterns), re.IGNORECASE)


def strip_progress_marker(text: str) -> tuple[str, Optional[int]]:
    """Remove hidden ``[[Qn]]`` progress tags from ``text``.

    Returns ``(cleaned_text, n)`` where ``n`` is the highest question number
    seen (or ``None`` if no tag was present). Used by both the voice output
    filter and the text-chat loop so participants never see the tag.
    """
    found: Optional[int] = None

    def _sub(match: re.Match) -> str:
        nonlocal found
        try:
            n = int(match.group(1))
        except (TypeError, ValueError):
            return ""
        if found is None or n > found:
            found = n
        return ""

    cleaned = PROGRESS_MARKER_RE.sub(_sub, text)
    return cleaned, found


def looks_like_clarification(text: str, language: str = "en") -> bool:
    """True if a user turn reads as a clarification/repeat request rather
    than an answer (e.g. "sorry?", "what do you mean by that?").

    ``language`` is the agent's configured interview language ("de",
    "de-DE", "es", ...); region suffixes are ignored.
    """
    text = (text or "").strip()
    if not text:
        return False
    lang = (language or "en").split("-")[0].split("_")[0].lower()
    if _clarification_re(lang).search(text):
        return True
    # Short question aimed back at the interviewer ("at what point?",
    # "you mean right now?"). Long answers that merely end with a question
    # mark are left alone. CJK has no spaces, so cap by characters there.
    if text.endswith(("?", "？")):
        if lang in ("zh", "ja", "ko"):
            return len(text) <= 20
        return len(text.split()) <= 12
    return False


# ── Progress marker ─────────────────────────────────────────────────────────
#
# When the progress bar is enabled, the model prefixes each main question with a
# hidden tag like ``[[Q3]]``. The tag never reaches the participant: the voice
# path strips it in StructuredOutputFilter, the text path strips it before
# sending. Probes, clarifications, and the closing carry no tag, so the bar only
# advances on main questions. A missed tag is harmless: the bar holds until the
# next tagged question.

PROGRESS_MARKER_RE = re.compile(r"\[\[\s*Q\s*(\d+)\s*\]\]", re.IGNORECASE)


def progress_marker_instruction(total: int) -> str:
    """Prompt fragment asking the model to emit the hidden progress tag."""
    return (
        "\n\n### Progress marker (hidden, required on EVERY main question)\n"
        f"This interview has {total} main questions, numbered 1 to {total}. "
        "Every single time you ask a MAIN question, begin that message with a "
        "hidden tag of the exact form [[Qn]], where n is the number of that "
        "main question. Your first main question starts with [[Q1]], your "
        f"second main question starts with [[Q2]], and so on up to [[Q{total}]]. "
        "This is not a one-time thing: tag the second, third, and every later "
        "main question too, not just the first. Do NOT add the tag to follow-up "
        "probes, clarification answers, acknowledgements, or the closing "
        "message. The tag is removed automatically before the participant sees "
        "or hears it, so never mention it, never read it aloud, and never "
        "explain it. Put nothing before the tag."
    )


# ── Prompt builder ──────────────────────────────────────────────────────────

def build_structured_prompt(
    base_prompt: str,
    guide: dict,
    emit_progress: bool = False,
) -> str:
    """
    Build a system prompt that encodes the interview guide.

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
- Ask probes from the list in order, picking a different one each turn.
  Do NOT invent additional probes of your own.
- Ask exactly ONE question per turn, then STOP and wait for the
  participant's answer. Never combine a probe with the next main question,
  and never move to the next main question in the same turn in which you
  asked something. Your reply must contain at most ONE question mark —
  everything you say after your first question is cut off before the
  participant hears it, so end your turn there.
- The transition phrases in the guide are stage directions for you. Never
  read labels like "Transition:" aloud and never write them in parentheses —
  say the phrase naturally as part of your sentence, or skip it.
- If the participant asks you a question or asks for clarification, answer
  it briefly (one or two sentences), then continue with the CURRENT probe
  or question. Answering a clarification does NOT count as a follow-up and
  does NOT advance the interview.
- Do NOT acknowledge or evaluate answers ("great", "interesting",
  "that's helpful"). A neutral "Mm-hm." or going straight to the next
  probe is correct. Validation biases the participant.
- Do NOT narrate ("let's move on", "now I'll ask a follow-up",
  "transitioning"). Just ask the next thing.
- When you reach the maximum follow-ups for a question, move on to the
  next main question, even if the participant's answers were brief.

{question_guide}

### Closing
After the final question's follow-ups are done AND the participant has given
their final answer, say exactly: "{closing}"
Never deliver the closing message in the same turn as a question, and never
deliver it while the participant is still waiting for you to repeat or
clarify something — answer them, wait for their reply, then close.

### Keeping track of where you are
Your own previous replies may appear split across several messages in the
history (for example an acknowledgment and a question shown separately).
Treat everything you said between two participant messages as ONE turn.
Before each turn, look at the conversation history and figure out:
1. Which question number are we on (1..{len(questions)})?
2. Which probes from this question's list have I already asked? Count
   follow-ups by matching the probes you actually asked, not by counting
   your own messages. Clarification answers do not count.
3. Therefore, what comes next: the next unused probe, or — only once the
   participant has answered and the follow-up budget is used — the next
   main question?

If unsure which probe you already asked, ask the next unused probe rather
than repeating one. Do not skip ahead to the next main question while
unused probes remain, unless the participant has already clearly covered
them or the protocol tells you to advance.
"""

    prompt = base_prompt.rstrip() + structured_section
    if emit_progress:
        prompt += progress_marker_instruction(len(questions))
    return prompt


# ── Structured output filter ────────────────────────────────────────────────
#
# Production sessions showed the model cramming several protocol steps into a
# single spoken turn despite the prompt's "ask exactly ONE question per turn"
# rule, e.g.:
#
#   "What was that experience like for you at the time?
#    (Transition: Thanks, that's really helpful background.)
#    Thinking about a specific recent moment, could you walk me through it?"
#
# — a probe, a leaked stage-direction label, and the NEXT main question all
# in one breath, which burned the whole interview in a couple of turns. The
# prompt alone cannot guarantee this never happens, so this filter enforces
# it on the output path: each LLM response is cut after its first question
# sentence, and "(Transition: ...)" label leakage is unwrapped to the bare
# phrase. The assistant context aggregator sits downstream, so the model's
# own history matches what was actually spoken.

_SENTENCE_RE = re.compile(r"[^.!?。！？…]*[.!?。！？…]+[\"'）)\]]*\s*", re.DOTALL)
_TRANSITION_LABEL_RE = re.compile(
    r"[(\[]\s*transition[^:：]*[:：]\s*([^)\]]*)[)\]]", re.IGNORECASE
)
_QUESTION_MARKS = ("?", "？")


class StructuredOutputFilter(FrameProcessor):
    """Enforces the one-question-per-turn protocol on the LLM's output.

    Place between the LLM and the TTS service (before the transcript logger,
    so persisted transcripts match what participants hear). Within each LLM
    response it:

    - buffers streamed ``TextFrame`` tokens and re-emits them sentence by
      sentence;
    - unwraps leaked stage directions ("(Transition: thanks!)" → "thanks!");
    - drops every sentence after the first one containing a question mark.

    Outside structured interviews the pipeline simply doesn't include this
    processor.

    When ``progress_callback`` is provided, hidden ``[[Qn]]`` tags are pulled
    out of the stream and reported (monotonically, clamped to
    ``total_questions``) so the participant UI can advance a progress bar. The
    tag is always removed before any text is pushed downstream to TTS.
    """

    def __init__(
        self,
        name: str = "StructuredOutputFilter",
        progress_callback=None,
        total_questions: int = 0,
    ):
        super().__init__(name=name)
        self._in_response = False
        self._pending = ""
        self._question_done = False
        self._dropped_chars = 0
        self._progress_callback = progress_callback
        self._total_questions = total_questions
        self._reported_progress = 0

    def _reset(self):
        self._in_response = False
        self._pending = ""
        self._question_done = False
        self._dropped_chars = 0

    async def _report_progress(self, question_number: int):
        """Report a main-question number to the UI: forward-only, clamped."""
        if not self._progress_callback:
            return
        n = question_number
        if self._total_questions:
            n = min(n, self._total_questions)
        if n <= self._reported_progress:
            return
        self._reported_progress = n
        try:
            await self._progress_callback(n, self._total_questions)
        except Exception as exc:  # progress is best-effort, never break the call
            logger.debug("[guide] progress callback failed: {}", exc)

    async def _emit_sentence(self, sentence: str, direction: FrameDirection):
        # Pull progress tags out first so they never reach TTS, even on a
        # sentence we go on to drop after the turn's first question.
        sentence, marker = strip_progress_marker(sentence)
        if marker is not None:
            await self._report_progress(marker)
        if self._question_done:
            self._dropped_chars += len(sentence)
            return
        cleaned = _TRANSITION_LABEL_RE.sub(r"\1", sentence)
        if cleaned.strip():
            await self.push_frame(TextFrame(text=cleaned), direction)
        if any(q in cleaned for q in _QUESTION_MARKS):
            self._question_done = True

    async def _drain_pending(self, direction: FrameDirection, final: bool):
        pos = 0
        for m in _SENTENCE_RE.finditer(self._pending):
            if m.start() != pos:
                break
            await self._emit_sentence(m.group(0), direction)
            pos = m.end()
        self._pending = self._pending[pos:]
        if final and self._pending:
            await self._emit_sentence(self._pending, direction)
            self._pending = ""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMFullResponseStartFrame):
            self._reset()
            self._in_response = True
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, LLMFullResponseEndFrame):
            await self._drain_pending(direction, final=True)
            if self._dropped_chars:
                logger.info(
                    "[guide] output filter cut {} chars after the turn's "
                    "first question",
                    self._dropped_chars,
                )
            self._reset()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, InterruptionFrame):
            self._reset()
            await self.push_frame(frame, direction)
            return

        if (
            self._in_response
            and direction == FrameDirection.DOWNSTREAM
            and isinstance(frame, TextFrame)
            and not isinstance(
                frame, (TranscriptionFrame, InterimTranscriptionFrame)
            )
        ):
            self._pending += frame.text
            await self._drain_pending(direction, final=False)
            return

        await self.push_frame(frame, direction)


# ── Shared protocol logic (framework-agnostic) ──────────────────────────────

DEFAULT_MAX_FOLLOW_UPS = 3

DEFAULT_CLOSING = "Thank you for your time. This concludes our interview."


def question_max_follow_ups(question: dict) -> int:
    """Per-question follow-up cap, defaulting safely on bad/missing values."""
    try:
        return int(question.get("max_follow_ups", DEFAULT_MAX_FOLLOW_UPS))
    except (TypeError, ValueError):
        return DEFAULT_MAX_FOLLOW_UPS


def build_protocol_guidance(
    questions: list[dict],
    closing: str,
    current_index: int,
) -> tuple[Optional[dict], bool]:
    """Build the mid-interview nudge that moves the agent forward.

    Returns ``(guidance_message_dict, is_closing)``. ``is_closing`` is True
    when ``current_index`` is the final question and the guidance asks the
    agent to wrap up rather than advance. The guidance is a provider-safe
    user-role note (see ``app.engagement.adaptive.guidance_message``).

    This is the single source of truth for advance/close wording, shared by
    the voice ``InterviewGuideProcessor`` and the text ``TextStructured
    Controller`` so both channels behave identically.
    """
    from app.engagement.adaptive import guidance_message

    next_idx = current_index + 1
    if next_idx >= len(questions):
        return (
            guidance_message(
                "[Interview protocol] You have completed all the questions "
                "in the guide. If the participant's last message was a "
                "question, answer it briefly first. Then acknowledge their "
                "answer briefly and deliver the closing message: "
                f'"{closing}". Do not ask any new interview questions, '
                "and never combine a question with the closing message in "
                "the same turn."
            ),
            True,
        )

    current_q = questions[current_index]
    next_q = questions[next_idx]
    transition = (current_q.get("transition") or "").strip()
    next_text = next_q.get("text", "")
    transition_hint = (
        f' Use this transition if it fits: "{transition}".' if transition else ""
    )
    return (
        guidance_message(
            f"[Interview protocol] You have explored question "
            f"{current_index + 1} of {len(questions)} sufficiently. If the "
            f"participant's last message was a question, answer it briefly "
            f"first. Then acknowledge their answer in one short sentence and "
            f'move on to question {next_idx + 1}: "{next_text}". Ask only '
            f"that question and wait for their answer."
            f"{transition_hint}"
        ),
        False,
    )


def enforce_one_question_per_turn(text: str) -> tuple[str, int]:
    """One-question-per-turn enforcement for a *complete* reply.

    The non-streaming twin of ``StructuredOutputFilter`` for callers that
    already hold the whole LLM message (the text-chat loop). It:

    - unwraps leaked stage directions ("(Transition: thanks!)" → "thanks!");
    - drops every sentence after the first one containing a question mark.

    Returns ``(cleaned_text, dropped_chars)``. Progress markers are NOT
    touched here — strip them with ``strip_progress_marker`` first if needed.
    """
    sentences: list[str] = []
    pos = 0
    for m in _SENTENCE_RE.finditer(text):
        if m.start() != pos:
            break
        sentences.append(m.group(0))
        pos = m.end()
    tail = text[pos:]
    if tail:
        sentences.append(tail)

    out: list[str] = []
    dropped = 0
    question_done = False
    for sentence in sentences:
        if question_done:
            dropped += len(sentence)
            continue
        cleaned = _TRANSITION_LABEL_RE.sub(r"\1", sentence)
        out.append(cleaned)
        if any(q in cleaned for q in _QUESTION_MARKS):
            question_done = True
    return "".join(out), dropped


# ── Stateful nudge processor (voice) ────────────────────────────────────────


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

    def __init__(
        self,
        guide: dict,
        language: str = "en",
        name: str = "InterviewGuideProcessor",
    ):
        super().__init__(name=name)
        self._guide = guide or {}
        self._language = language or "en"
        self._questions = list(self._guide.get("questions") or [])
        self._closing = self._guide.get("closing_message", DEFAULT_CLOSING)
        self.current_question_index = 0
        self._bot_turns_on_question = 0
        self._nudge_pending = False
        self._closed = False
        # Protocol-adherence counters (observability). These record how often
        # the safety net actually had to intervene, surfaced via ``stats()``
        # and logged once the interview closes.
        self._advances = 0
        self._nudges_injected = 0
        self._counted_bot_turns = 0
        # Bot turns that happen *before* the participant has spoken (the
        # spoken welcome message in particular) used to be counted against
        # question 1's follow-up budget, which made the agent advance after
        # the very first probe. We gate counting on having seen at least one
        # ``UserStoppedSpeakingFrame`` so the welcome is free.
        self._user_has_spoken = False
        # Everything the participant said since the last counted bot turn.
        # Used to recognize clarification requests so neither the budget
        # counter nor the advance/close nudge punishes them.
        self._user_buffer: list[str] = []

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
        return question_max_follow_ups(self._questions[self.current_question_index])

    def _build_advance_message(self) -> Optional[dict]:
        """Build the nudge message asking the LLM to move on.

        Delegates the wording to the shared ``build_protocol_guidance`` so the
        voice and text channels stay identical. The guidance is injected with
        the "user" role: several chat APIs (OpenAI gpt-5.x among them) reject a
        "system" message appearing after an assistant message with a 400 error,
        which would silence the agent for the rest of the session.
        """
        msg, is_closing = build_protocol_guidance(
            self._questions, self._closing, self.current_question_index
        )
        if is_closing:
            self._closed = True
        return msg

    # ── Frame handling ──────────────────────────────────────────────────

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            self.current_question_index = 0
            self._bot_turns_on_question = 0
            self._nudge_pending = False
            self._closed = False
            self._user_has_spoken = False
            self._user_buffer = []

        # Accumulate user speech so we can tell answers apart from
        # clarification requests. The buffer is cleared whenever a bot turn
        # is evaluated, so at any point it holds "what the participant said
        # since the agent last finished speaking".
        elif isinstance(frame, TranscriptionFrame):
            if frame.text and frame.text.strip():
                self._user_buffer.append(frame.text.strip())

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
            # The buffer holds the user turn this bot reply responded to.
            user_text = " ".join(self._user_buffer)
            self._user_buffer = []
            # Lock the counter until the participant speaks again. The
            # next TTS event (silence prompt, repeated greeting, etc.)
            # won't be counted unless a real user turn happens first.
            self._user_has_spoken = False
            if looks_like_clarification(user_text, self._language):
                # The agent was answering "what do you mean?" / repeating
                # itself — that is not a probe, so it must not burn the
                # question's follow-up budget.
                logger.debug(
                    "[guide] q={} bot turn not counted "
                    "(reply to clarification: {!r})",
                    self.current_question_index + 1,
                    user_text[:80],
                )
            else:
                self._bot_turns_on_question += 1
                self._counted_bot_turns += 1
                budget = 1 + self._current_max_follow_ups()
                logger.debug(
                    "[guide] q={} agent_turn={}/{}",
                    self.current_question_index + 1,
                    self._bot_turns_on_question,
                    budget,
                )
                if self._bot_turns_on_question >= budget:
                    self._nudge_pending = True

        # When the user finishes their reply and a nudge is pending, push a
        # system message before the LLM context aggregator triggers a run.
        elif isinstance(frame, UserStoppedSpeakingFrame):
            self._user_has_spoken = True
            if self._nudge_pending:
                # If what the participant just said is a clarification or
                # repeat request, hold the nudge: advancing (or worse,
                # closing) now would steamroll them. The model answers the
                # clarification this turn — uncounted, see above — and the
                # nudge fires on their next substantive turn instead.
                current_text = " ".join(self._user_buffer)
                if looks_like_clarification(current_text, self._language):
                    logger.info(
                        "[guide] q={} holding nudge — participant asked a "
                        "clarification: {!r}",
                        self.current_question_index + 1,
                        current_text[:80],
                    )
                    await self.push_frame(frame, direction)
                    return
                msg = self._build_advance_message()
                if msg is not None:
                    self._nudges_injected += 1
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
                        self._advances += 1
                    else:
                        logger.info(
                            "[guide] protocol summary: {}", self.stats()
                        )
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

    def stats(self) -> dict:
        """Protocol-adherence summary for observability/logging.

        ``forced_advances`` / ``nudges_injected`` being high relative to
        ``total_questions`` means the model was not advancing on its own and
        the safety net carried the interview — a signal to tune the prompt.
        """
        reached = (
            self.total_questions
            if self._closed
            else min(self.current_question_index + 1, self.total_questions)
        )
        return {
            "channel": "voice",
            "total_questions": self.total_questions,
            "questions_reached": reached,
            "completed": self._closed,
            "forced_advances": self._advances,
            "nudges_injected": self._nudges_injected,
            "counted_bot_turns": self._counted_bot_turns,
        }


# ── Stateful controller (text chat) ─────────────────────────────────────────


class TextStructuredController:
    """Structured-interview guardrail for the text-chat loop.

    The voice pipeline gets its guardrails from ``InterviewGuideProcessor``
    (turn budget + advance nudges) and ``StructuredOutputFilter`` (one
    question per turn). The text-chat loop historically had *neither*: it only
    fed the structured prompt to the model and hoped it complied, so the exact
    failure modes those guardrails exist to catch (looping on a question,
    never advancing, cramming several questions into one reply) were
    unmitigated in text. This controller closes that gap.

    The text loop is strictly alternating (assistant ↔ user) with no silence
    prompts or split STT frames, so the bookkeeping is simpler than the voice
    processor — no ``user_has_spoken`` gating is needed. The welcome message
    is appended directly to the context by the loop and never passed through
    ``register_bot_turn``, so it is free, matching the voice behaviour.

    Position is kept authoritative two ways: the turn-budget counter (as in
    voice) *and* ``sync_to_marker`` which trusts the model's own hidden
    ``[[Qn]]`` tag when present. The marker is the stronger signal — it is the
    model declaring which main question it just asked — so when it advances,
    the brittle heuristics (turn counting, clarification regex) defer to it.
    """

    def __init__(self, guide: dict, language: str = "en"):
        self._questions = list((guide or {}).get("questions") or [])
        self._closing = (guide or {}).get("closing_message", DEFAULT_CLOSING)
        self._language = language or "en"
        self.current_question_index = 0
        self._bot_turns_on_question = 0
        self._nudge_pending = False
        self._closed = False
        # Observability counters (mirror InterviewGuideProcessor.stats()).
        self._advances = 0
        self._nudges_injected = 0
        self._counted_bot_turns = 0
        self._max_index_reached = 0

    @property
    def total_questions(self) -> int:
        return len(self._questions)

    @property
    def is_finished(self) -> bool:
        return self._closed or self.current_question_index >= len(self._questions)

    def _current_max_follow_ups(self) -> int:
        if self.current_question_index >= len(self._questions):
            return DEFAULT_MAX_FOLLOW_UPS
        return question_max_follow_ups(self._questions[self.current_question_index])

    def maybe_advance_message(self, user_text: str) -> Optional[dict]:
        """Return a guidance message to inject *before* the next LLM call.

        Call once when a fresh participant message arrives. If the previous
        bot turn exhausted the current question's budget and this user turn is
        substantive (not a clarification/repeat request), state advances and a
        provider-safe guidance note is returned for the caller to append to
        the context. Otherwise returns ``None`` (nudge held or not pending).
        """
        if not self._nudge_pending or self._closed:
            return None
        if looks_like_clarification(user_text, self._language):
            logger.info(
                "[guide:text] q={} holding nudge — participant asked a "
                "clarification: {!r}",
                self.current_question_index + 1,
                (user_text or "")[:80],
            )
            return None
        msg, is_closing = build_protocol_guidance(
            self._questions, self._closing, self.current_question_index
        )
        self._nudge_pending = False
        if msg is None:
            return None
        self._nudges_injected += 1
        if is_closing:
            self._closed = True
            logger.info("[guide:text] protocol summary: {}", self.stats())
        else:
            logger.info(
                "[guide:text] advancing from q={} -> q={}",
                self.current_question_index + 1,
                self.current_question_index + 2,
            )
            self.current_question_index += 1
            self._max_index_reached = max(
                self._max_index_reached, self.current_question_index
            )
            self._bot_turns_on_question = 0
            self._advances += 1
        return msg

    def sync_to_marker(self, marker: Optional[int]) -> None:
        """Align state to the model's hidden ``[[Qn]]`` tag (1-based).

        Forward-only: a marker that matches or rewinds the current position is
        ignored. When the model advances itself we trust it — clearing any
        pending nudge and resetting the per-question counter — so the safety
        net never fights the model.
        """
        if marker is None:
            return
        idx = marker - 1
        if 0 <= idx < len(self._questions) and idx > self.current_question_index:
            logger.debug(
                "[guide:text] marker sync q={} -> q={}",
                self.current_question_index + 1,
                idx + 1,
            )
            self.current_question_index = idx
            self._max_index_reached = max(self._max_index_reached, idx)
            self._bot_turns_on_question = 0
            self._nudge_pending = False

    def register_bot_turn(self, prompting_user_text: str) -> None:
        """Account for one agent reply against the current question's budget.

        Call after each LLM reply, passing the participant message that
        prompted it. Replies that answer a clarification/repeat request do not
        count (mirrors the voice processor), so clarification exchanges never
        burn the follow-up budget.
        """
        if self._closed:
            return
        if looks_like_clarification(prompting_user_text, self._language):
            logger.debug(
                "[guide:text] q={} bot turn not counted (reply to "
                "clarification: {!r})",
                self.current_question_index + 1,
                (prompting_user_text or "")[:80],
            )
            return
        self._bot_turns_on_question += 1
        self._counted_bot_turns += 1
        budget = 1 + self._current_max_follow_ups()
        logger.debug(
            "[guide:text] q={} agent_turn={}/{}",
            self.current_question_index + 1,
            self._bot_turns_on_question,
            budget,
        )
        if self._bot_turns_on_question >= budget:
            self._nudge_pending = True

    def stats(self) -> dict:
        reached = (
            self.total_questions
            if self._closed
            else min(
                max(self.current_question_index, self._max_index_reached) + 1,
                self.total_questions,
            )
        )
        return {
            "channel": "text",
            "total_questions": self.total_questions,
            "questions_reached": reached,
            "completed": self._closed,
            "forced_advances": self._advances,
            "nudges_injected": self._nudges_injected,
            "counted_bot_turns": self._counted_bot_turns,
        }

    def snapshot(self) -> dict:
        return {
            "current_question_index": self.current_question_index,
            "bot_turns_on_question": self._bot_turns_on_question,
            "nudge_pending": self._nudge_pending,
            "closed": self._closed,
            "total_questions": self.total_questions,
        }


__all__ = [
    "build_structured_prompt",
    "looks_like_clarification",
    "strip_progress_marker",
    "enforce_one_question_per_turn",
    "build_protocol_guidance",
    "question_max_follow_ups",
    "InterviewGuideProcessor",
    "StructuredOutputFilter",
    "TextStructuredController",
    "DEFAULT_MAX_FOLLOW_UPS",
    "DEFAULT_CLOSING",
]
