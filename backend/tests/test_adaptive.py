"""Tests for the adaptive behavior policy engine."""

import uuid

import pytest
from sqlalchemy import select

from app.engagement.adaptive import (
    ACTION_CATALOG,
    PROMPT,
    TTS_SPEED,
    AdaptivePolicy,
    AdaptivePolicyEngine,
    AdaptiveSignals,
)


def _policy(rules, mode="shadow"):
    return AdaptivePolicy.from_dict({"mode": mode, "rules": rules})


def test_from_dict_drops_unknown_triggers_and_actions():
    p = AdaptivePolicy.from_dict(
        {
            "mode": "live",
            "rules": [
                {"on": "sustained_disengagement", "action": "offer_break"},
                {"on": "nope", "action": "offer_break"},
                {"on": "long_latency", "action": "nope"},
            ],
        }
    )
    assert p.mode == "live"
    assert len(p.rules) == 1
    assert p.rules[0].action == "offer_break"


def test_invalid_mode_defaults_to_shadow():
    assert AdaptivePolicy.from_dict({"mode": "weird", "rules": []}).mode == "shadow"
    assert AdaptivePolicy.from_dict(None).mode == "shadow"


def test_signals_triggers_filters_to_known():
    s = AdaptiveSignals(
        events=["sustained_disengagement"], flags=["long_latency", "garbage"]
    )
    assert s.triggers() == {"sustained_disengagement", "long_latency"}


def test_prompt_action_uses_default_instruction():
    engine = AdaptivePolicyEngine(
        _policy([{"on": "sustained_disengagement", "action": "offer_break"}])
    )
    actions = engine.evaluate({"sustained_disengagement"}, now=0.0)
    assert len(actions) == 1
    a = actions[0]
    assert a.type == PROMPT
    assert a.action == "offer_break"
    assert a.instruction == ACTION_CATALOG["offer_break"].default_instruction


def test_prompt_action_custom_instruction_overrides():
    engine = AdaptivePolicyEngine(
        _policy(
            [
                {
                    "on": "long_latency",
                    "action": "soften_next_probe",
                    "custom_instruction": "Be extra gentle.",
                }
            ]
        )
    )
    a = engine.evaluate({"long_latency"}, now=0.0)[0]
    assert a.instruction == "Be extra gentle."


def test_speed_action_clamped():
    engine = AdaptivePolicyEngine(
        _policy(
            [{"on": "long_latency", "action": "slow_down", "params": {"speed": 0.2}}]
        )
    )
    a = engine.evaluate({"long_latency"}, now=0.0)[0]
    assert a.type == TTS_SPEED
    assert a.params["speed"] == 0.7  # clamped to min


def test_one_prompt_and_one_speed_per_turn():
    engine = AdaptivePolicyEngine(
        _policy(
            [
                {"on": "sustained_disengagement", "action": "offer_break"},
                {"on": "sustained_disengagement", "action": "privacy_check"},
                {"on": "sustained_disengagement", "action": "slow_down"},
                {"on": "sustained_disengagement", "action": "reset_pace"},
            ]
        )
    )
    actions = engine.evaluate({"sustained_disengagement"}, now=0.0)
    types = [a.type for a in actions]
    assert types.count(PROMPT) == 1
    assert types.count(TTS_SPEED) == 1
    # First matching rule of each type wins.
    assert actions[0].action == "offer_break"


def test_cooldown_blocks_then_allows():
    engine = AdaptivePolicyEngine(
        _policy(
            [
                {
                    "on": "long_latency",
                    "action": "offer_break",
                    "cooldown_seconds": 30,
                }
            ]
        )
    )
    assert engine.evaluate({"long_latency"}, now=0.0)  # fires
    assert engine.evaluate({"long_latency"}, now=10.0) == []  # within cooldown
    assert engine.evaluate({"long_latency"}, now=40.0)  # cooldown elapsed


def test_no_trigger_no_action():
    engine = AdaptivePolicyEngine(
        _policy([{"on": "long_latency", "action": "offer_break"}])
    )
    assert engine.evaluate({"high_filler"}, now=0.0) == []


def test_supports_tts_speed_helper():
    from app.pipeline.adaptive_processor import supports_tts_speed

    assert supports_tts_speed("elevenlabs")
    assert supports_tts_speed("OpenAI")
    assert not supports_tts_speed("azure")
    assert not supports_tts_speed(None)


def test_pace_via_instructions_only_for_openai_gpt4o_tts():
    """OpenAI's numeric ``speed`` is post-synthesis time-stretching and
    distorts the voice; gpt-4o TTS models take prosody instructions instead.
    ElevenLabs/Cartesia render the requested speed natively, so they keep
    the numeric parameter."""
    from app.pipeline.adaptive_processor import pace_via_instructions

    assert pace_via_instructions("openai", "gpt-4o-mini-tts")
    assert pace_via_instructions("openai", None)  # default model is gpt-4o-mini-tts
    assert not pace_via_instructions("openai", "tts-1")
    assert not pace_via_instructions("elevenlabs", "gpt-4o-mini-tts")
    assert not pace_via_instructions("cartesia", None)
    assert not pace_via_instructions(None, None)


def test_pace_instruction_mapping():
    from app.pipeline.adaptive_processor import pace_instruction

    assert "slowly and calmly" in pace_instruction(0.8)
    assert "slightly slower" in pace_instruction(0.95)
    assert "natural" in pace_instruction(1.0)
    assert "brisker" in pace_instruction(1.1)


def test_match_style_action_in_catalog():
    spec = ACTION_CATALOG["match_style"]
    assert spec.type == PROMPT
    assert "mirror" in spec.default_instruction.lower()
    engine = AdaptivePolicyEngine(
        _policy([{"on": "positive_engagement_streak", "action": "match_style"}])
    )
    a = engine.evaluate({"positive_engagement_streak"}, now=0.0)[0]
    assert a.instruction == spec.default_instruction


# ── Text-chat adaptation path ────────────────────────────────


@pytest.mark.asyncio
async def test_text_adaptation_live_injects_and_records(
    db_session_factory, monkeypatch
):
    import app.api.text_chat as tc
    from app.models.engagement import AdaptiveAction

    monkeypatch.setattr(tc, "async_session_factory", db_session_factory)

    engine = AdaptivePolicyEngine(
        _policy(
            [{"on": "very_short_answer", "action": "encourage_elaboration"}],
            mode="live",
        )
    )
    session_id = uuid.uuid4()
    messages = [{"role": "system", "content": "base"}]

    await tc._apply_text_adaptation(
        session_id,
        engine,
        sequence=4,
        triggers={"very_short_answer"},
        messages=messages,
    )

    # Live mode appends a system instruction before the next LLM call.
    # Injected as a marked user-role note — mid-conversation system messages
    # are rejected by some chat APIs (OpenAI gpt-5.x).
    assert messages[-1]["role"] == "user"
    assert "interviewer guidance" in messages[-1]["content"].lower()
    assert "invite them to say more" in messages[-1]["content"].lower()

    async with db_session_factory() as db:
        rows = (
            (await db.execute(select(AdaptiveAction).where(
                AdaptiveAction.session_id == session_id
            ))).scalars().all()
        )
    assert len(rows) == 1
    assert rows[0].action == "encourage_elaboration"
    assert rows[0].mode == "live"
    assert rows[0].detail["applied"] is True


@pytest.mark.asyncio
async def test_text_adaptation_shadow_records_only(db_session_factory, monkeypatch):
    import app.api.text_chat as tc
    from app.models.engagement import AdaptiveAction

    monkeypatch.setattr(tc, "async_session_factory", db_session_factory)

    engine = AdaptivePolicyEngine(
        _policy(
            [{"on": "very_short_answer", "action": "encourage_elaboration"}],
            mode="shadow",
        )
    )
    session_id = uuid.uuid4()
    messages = [{"role": "system", "content": "base"}]

    await tc._apply_text_adaptation(
        session_id,
        engine,
        sequence=1,
        triggers={"very_short_answer"},
        messages=messages,
    )

    # Shadow mode must not change the conversation.
    assert len(messages) == 1

    async with db_session_factory() as db:
        rows = (
            (await db.execute(select(AdaptiveAction).where(
                AdaptiveAction.session_id == session_id
            ))).scalars().all()
        )
    assert len(rows) == 1
    assert rows[0].mode == "shadow"
    assert rows[0].detail["applied"] is False


@pytest.mark.asyncio
async def test_text_adaptation_speed_action_is_noop_for_text(
    db_session_factory, monkeypatch
):
    import app.api.text_chat as tc
    from app.models.engagement import AdaptiveAction

    monkeypatch.setattr(tc, "async_session_factory", db_session_factory)

    engine = AdaptivePolicyEngine(
        _policy([{"on": "long_latency", "action": "slow_down"}], mode="live")
    )
    session_id = uuid.uuid4()
    messages = [{"role": "system", "content": "base"}]

    await tc._apply_text_adaptation(
        session_id,
        engine,
        sequence=2,
        triggers={"long_latency"},
        messages=messages,
    )

    assert len(messages) == 1  # speed can't apply to text
    async with db_session_factory() as db:
        rows = (
            (await db.execute(select(AdaptiveAction).where(
                AdaptiveAction.session_id == session_id
            ))).scalars().all()
        )
    assert len(rows) == 1
    assert rows[0].detail["applied"] is False
    assert rows[0].detail.get("note") == "speed_not_applicable_to_text"
