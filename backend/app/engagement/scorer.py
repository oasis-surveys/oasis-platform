"""
OASIS — Rule-based engagement scorer (config-driven).

Transparent, tunable thresholds map raw per-turn features to a 0..1 score,
a coarse label, and a list of per-turn flags. No model, no training data;
researchers can read exactly why a turn scored the way it did.

Thresholds live in ``ScorerConfig`` and can be overridden per agent via the
``engagement_config`` field. Missing keys fall back to the defaults below, so
an agent only needs to store the values it actually changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.engagement.features import TurnFeatures


@dataclass
class ScorerConfig:
    # Component weights; only components present for a turn are used, then the
    # score is renormalized over the available weight.
    weight_length: float = 0.35
    weight_latency: float = 0.25
    weight_rate: float = 0.15
    weight_fillers: float = 0.15
    weight_energy: float = 0.10

    # Feature thresholds.
    latency_fast_ms: int = 300
    latency_slow_ms: int = 4000
    words_full_credit: int = 25
    rate_band_low_wpm: int = 90
    rate_band_high_wpm: int = 170
    rate_taper_wpm: int = 80
    filler_ratio_zero_credit: float = 0.15
    energy_full_credit: float = 0.12

    # Labels.
    low_threshold: float = 0.34
    high_threshold: float = 0.67

    # Per-turn flags.
    long_latency_ms: int = 4000
    short_answer_words: int = 3

    # Rolling window for event detection.
    window_size: int = 3

    @classmethod
    def for_modality(cls, modality: str) -> "ScorerConfig":
        """Base defaults for a modality.

        Text answers involve reading + typing, so response latency runs much
        longer than spoken latency and energy/speech-rate do not exist. The
        text profile widens latency thresholds and reweights toward length and
        lexical hedging.
        """
        cfg = cls()
        if modality == "text":
            cfg.latency_fast_ms = 4000
            cfg.latency_slow_ms = 60000
            cfg.long_latency_ms = 45000
            cfg.words_full_credit = 30
            cfg.weight_length = 0.5
            cfg.weight_latency = 0.2
            cfg.weight_fillers = 0.3
            cfg.weight_rate = 0.0
            cfg.weight_energy = 0.0
        return cfg

    @classmethod
    def from_dict(cls, data: dict | None, modality: str = "voice") -> "ScorerConfig":
        """Build a config from a (possibly partial) dict over modality defaults."""
        cfg = cls.for_modality(modality)
        if not data:
            return cfg
        weights = data.get("weights") or {}
        mapping = {
            "weight_length": weights.get("length"),
            "weight_latency": weights.get("latency"),
            "weight_rate": weights.get("rate"),
            "weight_fillers": weights.get("fillers"),
            "weight_energy": weights.get("energy"),
        }
        for attr in (
            "latency_fast_ms",
            "latency_slow_ms",
            "words_full_credit",
            "rate_band_low_wpm",
            "rate_band_high_wpm",
            "rate_taper_wpm",
            "filler_ratio_zero_credit",
            "energy_full_credit",
            "low_threshold",
            "high_threshold",
            "long_latency_ms",
            "short_answer_words",
            "window_size",
        ):
            if data.get(attr) is not None:
                mapping[attr] = data[attr]
        for attr, value in mapping.items():
            if value is not None:
                setattr(cfg, attr, value)
        return cfg


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass
class TurnScore:
    score: float
    label: str
    flags: list[str] = field(default_factory=list)
    components: dict[str, float] = field(default_factory=dict)


class RuleBasedScorer:
    """Stateless per-turn scorer driven by a ``ScorerConfig``."""

    def __init__(self, config: ScorerConfig | None = None):
        self.config = config or ScorerConfig()

    def _length_score(self, words: int) -> float:
        return _clamp(words / self.config.words_full_credit)

    def _latency_score(self, latency_ms: int) -> float:
        c = self.config
        span = max(1, c.latency_slow_ms - c.latency_fast_ms)
        return _clamp(1.0 - (latency_ms - c.latency_fast_ms) / span)

    def _rate_score(self, wpm: float) -> float:
        c = self.config
        if c.rate_band_low_wpm <= wpm <= c.rate_band_high_wpm:
            return 1.0
        taper = max(1, c.rate_taper_wpm)
        if wpm < c.rate_band_low_wpm:
            return _clamp(1.0 - (c.rate_band_low_wpm - wpm) / taper)
        return _clamp(1.0 - (wpm - c.rate_band_high_wpm) / taper)

    def _filler_score(self, filler_count: int, words: int) -> float:
        if words <= 0:
            return 1.0
        ratio = filler_count / words
        return _clamp(1.0 - ratio / self.config.filler_ratio_zero_credit)

    def _energy_score(self, rms: float) -> float:
        return _clamp(rms / self.config.energy_full_credit)

    def score(self, features: TurnFeatures) -> TurnScore:
        c = self.config
        weights = {
            "length": c.weight_length,
            "latency": c.weight_latency,
            "rate": c.weight_rate,
            "fillers": c.weight_fillers,
            "energy": c.weight_energy,
        }
        components: dict[str, float] = {}
        words = features.word_count or 0

        if features.word_count is not None:
            components["length"] = round(self._length_score(words), 3)
        if features.response_latency_ms is not None:
            components["latency"] = round(self._latency_score(features.response_latency_ms), 3)
        if features.speech_rate_wpm is not None:
            components["rate"] = round(self._rate_score(features.speech_rate_wpm), 3)
        if features.filler_count is not None and features.word_count is not None:
            components["fillers"] = round(self._filler_score(features.filler_count, words), 3)
        if features.rms_energy is not None:
            components["energy"] = round(self._energy_score(features.rms_energy), 3)

        weighted_sum = 0.0
        used_weight = 0.0
        for key, value in components.items():
            weighted_sum += value * weights[key]
            used_weight += weights[key]

        score = round(weighted_sum / used_weight, 3) if used_weight else 0.0

        if score < c.low_threshold:
            label = "low"
        elif score >= c.high_threshold:
            label = "high"
        else:
            label = "medium"

        flags: list[str] = []
        if (
            features.response_latency_ms is not None
            and features.response_latency_ms >= c.long_latency_ms
        ):
            flags.append("long_latency")
        if features.word_count is not None and words < c.short_answer_words:
            flags.append("very_short_answer")
        if (
            features.filler_count is not None
            and words > 0
            and features.filler_count / words >= c.filler_ratio_zero_credit
        ):
            flags.append("high_filler")

        return TurnScore(score=score, label=label, flags=flags, components=components)
