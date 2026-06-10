"""
OASIS — Adaptive behavior policy engine (Phase 3a).

Maps engagement triggers (events and per-turn flags) to a small, curated set
of actions: inject a system instruction before the next agent turn, or adjust
the agent's speaking pace. Everything is logged; in ``shadow`` mode actions are
recorded but not applied.

This module is pure logic. The pipeline processor and the text-chat loop own
the side effects (pushing frames / appending messages) and persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Triggers a rule can fire on: rolling-window events plus per-turn flags.
VALID_TRIGGERS = {
    "sustained_disengagement",
    "positive_engagement_streak",
    "recovery_after_dip",
    "long_latency",
    "very_short_answer",
    "high_filler",
}

# Action type markers.
PROMPT = "prompt"
TTS_SPEED = "tts_speed"

SPEED_MIN = 0.7
SPEED_MAX = 1.2


@dataclass(frozen=True)
class ActionSpec:
    id: str
    label: str
    type: str
    default_instruction: Optional[str] = None
    default_params: dict = field(default_factory=dict)


# Curated, reviewable catalog. Researchers pick from these; a rule may override
# a prompt action's text with its own ``custom_instruction``.
ACTION_CATALOG: dict[str, ActionSpec] = {
    "offer_break": ActionSpec(
        "offer_break",
        "Offer a break",
        PROMPT,
        "The participant has shown signs of fatigue or disengagement over the "
        "last few turns. Gently offer a short break or to move to a lighter "
        "topic. Keep it brief and warm. Do not mention that this was detected "
        "automatically.",
    ),
    "soften_next_probe": ActionSpec(
        "soften_next_probe",
        "Soften the next question",
        PROMPT,
        "Make your next question gentler and less probing. Lead with warmth and "
        "give the participant room to answer at their own pace.",
    ),
    "encourage_elaboration": ActionSpec(
        "encourage_elaboration",
        "Encourage elaboration",
        PROMPT,
        "The participant's recent answers have been brief. Warmly invite them to "
        "say more with a single open follow-up question.",
    ),
    "acknowledge_effort": ActionSpec(
        "acknowledge_effort",
        "Acknowledge engagement",
        PROMPT,
        "Briefly acknowledge the participant's effort and engagement before "
        "continuing with the interview.",
    ),
    "privacy_check": ActionSpec(
        "privacy_check",
        "Check in on comfort",
        PROMPT,
        "Check in about the participant's comfort and privacy in one short, warm "
        "sentence before continuing.",
    ),
    "slow_down": ActionSpec(
        "slow_down",
        "Slow speaking pace",
        TTS_SPEED,
        default_params={"speed": 0.9},
    ),
    "reset_pace": ActionSpec(
        "reset_pace",
        "Reset speaking pace",
        TTS_SPEED,
        default_params={"speed": 1.0},
    ),
}


def _clamp_speed(value: float) -> float:
    return max(SPEED_MIN, min(SPEED_MAX, value))


# Mid-conversation guidance is injected with the "user" role. Several chat
# APIs (OpenAI gpt-5.x among them) reject a "system" message that appears
# after an assistant message ("Unexpected role 'system' after role
# 'assistant'", HTTP 400), which silenced the agent for the rest of the
# session. A clearly marked user-role note works across all providers.
GUIDANCE_PREFIX = (
    "[Interviewer guidance — this is an instruction for you, not something "
    "the participant said. Follow it silently; never read it aloud, quote "
    "it, or mention it.]"
)


def guidance_message(instruction: str) -> dict:
    """Build a provider-safe mid-conversation guidance message."""
    return {"role": "user", "content": f"{GUIDANCE_PREFIX} {instruction}"}


@dataclass
class AdaptiveSignals:
    """Per-turn engagement result shared from the engagement processor.

    ``turn_id`` increments each time a complete turn has been scored, so the
    adaptive processor acts exactly once per turn even when segmented STT
    pushes several TranscriptionFrames through the pipeline.
    """

    turn_id: int = 0
    transcript_sequence: int = 0
    score: Optional[float] = None
    label: Optional[str] = None
    events: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    def triggers(self) -> set[str]:
        return {t for t in (*self.events, *self.flags) if t in VALID_TRIGGERS}


@dataclass
class AdaptiveRule:
    on: str
    action: str
    custom_instruction: Optional[str] = None
    cooldown_seconds: int = 0
    params: dict = field(default_factory=dict)


@dataclass
class ResolvedAction:
    action: str
    trigger: str
    type: str
    instruction: Optional[str] = None
    params: dict = field(default_factory=dict)


class AdaptivePolicy:
    def __init__(self, mode: str = "shadow", rules: Optional[list[AdaptiveRule]] = None):
        self.mode = mode if mode in ("shadow", "live") else "shadow"
        self.rules = rules or []

    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "AdaptivePolicy":
        if not data:
            return cls()
        rules: list[AdaptiveRule] = []
        for r in data.get("rules") or []:
            on = r.get("on")
            action = r.get("action")
            if on not in VALID_TRIGGERS or action not in ACTION_CATALOG:
                continue
            rules.append(
                AdaptiveRule(
                    on=on,
                    action=action,
                    custom_instruction=(r.get("custom_instruction") or None),
                    cooldown_seconds=int(r.get("cooldown_seconds") or 0),
                    params=dict(r.get("params") or {}),
                )
            )
        return cls(mode=data.get("mode") or "shadow", rules=rules)


class AdaptivePolicyEngine:
    """Stateful per-session evaluator. Holds rule cooldown timestamps."""

    def __init__(self, policy: AdaptivePolicy):
        self.policy = policy
        self._last_fired: dict[int, float] = {}

    def _resolve(self, rule: AdaptiveRule) -> Optional[ResolvedAction]:
        spec = ACTION_CATALOG.get(rule.action)
        if spec is None:
            return None
        if spec.type == PROMPT:
            instruction = rule.custom_instruction or spec.default_instruction
            return ResolvedAction(
                action=spec.id, trigger=rule.on, type=PROMPT, instruction=instruction
            )
        # tts_speed
        raw = rule.params.get("speed", spec.default_params.get("speed", 1.0))
        try:
            speed = _clamp_speed(float(raw))
        except (TypeError, ValueError):
            speed = 1.0
        return ResolvedAction(
            action=spec.id, trigger=rule.on, type=TTS_SPEED, params={"speed": speed}
        )

    def evaluate(self, triggers: set[str], now: float) -> list[ResolvedAction]:
        """
        Return actions to take for this turn.

        At most one prompt action and one speed action fire per turn (first
        match by rule order wins), and each rule respects its cooldown.
        """
        chosen: list[ResolvedAction] = []
        have_prompt = False
        have_speed = False

        for idx, rule in enumerate(self.policy.rules):
            if rule.on not in triggers:
                continue
            spec = ACTION_CATALOG.get(rule.action)
            if spec is None:
                continue
            if spec.type == PROMPT and have_prompt:
                continue
            if spec.type == TTS_SPEED and have_speed:
                continue
            last = self._last_fired.get(idx)
            if last is not None and (now - last) < rule.cooldown_seconds:
                continue
            resolved = self._resolve(rule)
            if resolved is None:
                continue
            chosen.append(resolved)
            self._last_fired[idx] = now
            if spec.type == PROMPT:
                have_prompt = True
            else:
                have_speed = True

        return chosen
