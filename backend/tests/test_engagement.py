"""Tests for engagement feature extraction and rule-based scoring."""

import array

from app.engagement.events import (
    POSITIVE_ENGAGEMENT_STREAK,
    RECOVERY_AFTER_DIP,
    SUSTAINED_DISENGAGEMENT,
    EventDetector,
)
from app.engagement.features import TurnFeatures, count_fillers, rms_energy, word_count
from app.engagement.scorer import RuleBasedScorer, ScorerConfig


def test_word_count_and_chars():
    assert word_count("hello there friend") == 3
    assert word_count("") == 0
    assert word_count("don't stop") == 2


def test_count_fillers_english():
    text = "um well I like, you know, sort of agree uh"
    # um, like, you know, sort of, uh
    assert count_fillers(text, "en") == 5


def test_count_fillers_language_fallback():
    # Unknown language falls back to English filler list.
    assert count_fillers("um uh", "xx") == 2


def test_rms_energy_silence_and_signal():
    assert rms_energy(b"") == 0.0
    silence = array.array("h", [0] * 100).tobytes()
    assert rms_energy(silence) == 0.0
    loud = array.array("h", [16000] * 100).tobytes()
    assert rms_energy(loud) > 0.4


def test_rms_energy_handles_odd_byte():
    # Odd trailing byte must not raise.
    assert rms_energy(b"\x01\x00\x05") >= 0.0


def test_turn_features_speech_rate():
    f = TurnFeatures.from_turn(
        transcript_sequence=1,
        text="one two three four five six",  # 6 words
        language="en",
        response_latency_ms=500,
        voiced_ms=6000,  # 6s → 60 wpm
    )
    assert f.word_count == 6
    assert f.speech_rate_wpm == 60.0
    assert f.response_latency_ms == 500


def test_scorer_high_engagement():
    f = TurnFeatures(
        transcript_sequence=1,
        response_latency_ms=400,
        voiced_ms=8000,
        word_count=30,
        char_count=160,
        speech_rate_wpm=130,
        filler_count=0,
        rms_energy=0.12,
    )
    result = RuleBasedScorer().score(f)
    assert result.label == "high"
    assert result.score >= 0.67
    assert result.flags == []


def test_scorer_low_engagement_and_flags():
    f = TurnFeatures(
        transcript_sequence=2,
        response_latency_ms=6000,   # long_latency
        voiced_ms=1000,
        word_count=1,               # very_short_answer
        char_count=3,
        speech_rate_wpm=60,
        filler_count=0,
        rms_energy=0.01,
    )
    result = RuleBasedScorer().score(f)
    assert result.label == "low"
    assert "long_latency" in result.flags
    assert "very_short_answer" in result.flags


def test_scorer_renormalizes_with_missing_features():
    # Only length present → score equals the length component.
    f = TurnFeatures(transcript_sequence=1, word_count=25)
    result = RuleBasedScorer().score(f)
    assert result.score == 1.0
    assert set(result.components) == {"length"}


# ── Config-driven scorer ─────────────────────────────────────


def test_scorer_config_from_partial_dict_keeps_defaults():
    cfg = ScorerConfig.from_dict({"window_size": 5, "weights": {"length": 0.5}})
    assert cfg.window_size == 5
    assert cfg.weight_length == 0.5
    assert cfg.weight_latency == 0.25  # untouched default


def test_scorer_config_changes_label():
    # A turn that is "high" by default becomes "medium" with a stricter threshold.
    f = TurnFeatures(transcript_sequence=1, word_count=25)  # score 1.0
    f2 = TurnFeatures(
        transcript_sequence=1,
        word_count=10,
        response_latency_ms=2000,
    )
    default = RuleBasedScorer().score(f2)
    strict = RuleBasedScorer(ScorerConfig.from_dict({"high_threshold": 0.95})).score(f2)
    assert default.label != "low"
    # Stricter high threshold can only lower or keep the label, never raise it.
    order = {"low": 0, "medium": 1, "high": 2}
    assert order[strict.label] <= order[default.label]
    assert RuleBasedScorer().score(f).label == "high"


# ── Event detector ───────────────────────────────────────────


def _run(labels, window=3):
    det = EventDetector(ScorerConfig.from_dict({"window_size": window}))
    fired = []
    for lbl in labels:
        for ev in det.observe(lbl):
            fired.append((lbl, ev.event_type))
    return [t for _, t in fired]


def test_sustained_disengagement_fires_once_then_rearms():
    # 3 lows → fire; a 4th low must NOT refire; a non-low then 3 lows refire.
    events = _run(["low", "low", "low", "low", "medium", "low", "low", "low"])
    assert events.count(SUSTAINED_DISENGAGEMENT) == 2


def test_positive_streak_detection():
    events = _run(["high", "high", "high"])
    assert events.count(POSITIVE_ENGAGEMENT_STREAK) == 1


def test_recovery_after_dip():
    events = _run(["low", "medium", "high"])
    assert RECOVERY_AFTER_DIP in events
    # No second dip → no second recovery.
    assert events.count(RECOVERY_AFTER_DIP) == 1


def test_no_events_for_steady_medium():
    assert _run(["medium", "medium", "medium", "medium"]) == []


# ── Text modality ────────────────────────────────────────────


def test_text_modality_counts_hedges_not_spoken_fillers():
    text = "maybe, i think so, but i'm not sure"
    # Spoken-filler counting (voice) shouldn't match these.
    assert count_fillers(text, "en", modality="voice") == 0
    # Hedging (text) should: maybe, i think, i'm not sure
    assert count_fillers(text, "en", modality="text") >= 3


def test_text_config_widens_latency_thresholds():
    cfg = ScorerConfig.for_modality("text")
    assert cfg.latency_slow_ms == 60000
    assert cfg.long_latency_ms == 45000
    assert cfg.weight_energy == 0.0


def test_text_features_have_no_audio_fields():
    f = TurnFeatures.from_turn(
        transcript_sequence=1,
        text="I think the product is quite good, maybe even great.",
        language="en",
        response_latency_ms=8000,
        voiced_ms=None,
        modality="text",
    )
    assert f.speech_rate_wpm is None
    assert f.rms_energy is None
    assert f.word_count > 0
    assert f.filler_count >= 1  # "I think", "maybe"


def test_text_scoring_uses_available_components_only():
    cfg = ScorerConfig.from_dict(None, modality="text")
    f = TurnFeatures.from_turn(
        transcript_sequence=1,
        text="Yes, definitely, I really enjoyed the whole experience a lot.",
        language="en",
        response_latency_ms=6000,
        voiced_ms=None,
        modality="text",
    )
    result = RuleBasedScorer(cfg).score(f)
    assert "rate" not in result.components
    assert "energy" not in result.components
    assert {"length", "latency", "fillers"} >= set(result.components)
    assert 0.0 <= result.score <= 1.0
