"""
OASIS — Per-turn engagement feature extraction.

Pure-Python helpers so the default deployment needs no extra dependencies
and nothing here blocks the audio pipeline meaningfully. Heavier acoustic
features (pitch tracking, speaker change) are intentionally deferred.
"""

from __future__ import annotations

import array
import re
from dataclasses import asdict, dataclass
from typing import Optional

# Filler words by language prefix. Keys match the agent ``language`` field's
# first two characters (e.g. "en", "de"). Falls back to English.
FILLER_WORDS: dict[str, tuple[str, ...]] = {
    "en": ("um", "uh", "erm", "like", "you know", "i mean", "sort of", "kind of"),
    "de": ("äh", "ähm", "halt", "also", "quasi", "sozusagen"),
    "es": ("eh", "este", "o sea", "pues", "bueno"),
    "fr": ("euh", "bah", "ben", "genre", "tu vois"),
}

# Lexical hedging for text interviews. Spoken fillers ("um", "uh") rarely show
# up in typed answers, so for text we count hedging/uncertainty markers instead.
HEDGE_WORDS: dict[str, tuple[str, ...]] = {
    "en": (
        "maybe", "perhaps", "i guess", "i think", "i suppose", "probably",
        "sort of", "kind of", "i'm not sure", "not sure", "or something",
        "i dunno", "i don't know",
    ),
    "de": ("vielleicht", "ich glaube", "ich denke", "wahrscheinlich", "irgendwie", "weiß nicht"),
    "es": ("quizás", "tal vez", "creo que", "supongo", "probablemente", "no sé"),
    "fr": ("peut-être", "je pense", "je crois", "je suppose", "probablement", "je sais pas"),
}

_WORD_RE = re.compile(r"\b[\w']+\b", re.UNICODE)


def _lexical_list(language: Optional[str], modality: str) -> tuple[str, ...]:
    table = HEDGE_WORDS if modality == "text" else FILLER_WORDS
    if not language:
        return table["en"]
    return table.get(language[:2].lower(), table["en"])


def word_count(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


def count_fillers(
    text: str, language: Optional[str] = None, modality: str = "voice"
) -> int:
    """
    Count filler/hedging tokens in a turn (case-insensitive).

    For voice this counts spoken fillers ("um", "uh"); for text it counts
    lexical hedging ("maybe", "i think"), which is the typed-answer analogue.
    """
    if not text:
        return 0
    lowered = text.lower()
    total = 0
    for token in _lexical_list(language, modality):
        if " " in token:
            total += lowered.count(token)
        else:
            total += len(re.findall(rf"\b{re.escape(token)}\b", lowered))
    return total


# Cap the number of samples inspected per turn. The mean-abs estimate is
# statistically stable well below this; it keeps the pure-Python loop bounded
# (~6ms) even for a 60-second turn, since it runs on the pipeline's turn path.
_MAX_RMS_SAMPLES = 100_000


def rms_energy(pcm: bytes) -> float:
    """
    Mean normalized amplitude (0..1) of 16-bit mono PCM.

    Returns 0.0 for empty input. Long turns are strided down to at most
    ``_MAX_RMS_SAMPLES`` samples so the cost stays bounded; uses the stdlib
    ``array`` module so there is no NumPy dependency.
    """
    if not pcm:
        return 0.0
    # Drop a trailing odd byte if a frame boundary was split.
    if len(pcm) % 2:
        pcm = pcm[:-1]
    if not pcm:
        return 0.0
    samples = array.array("h")
    samples.frombytes(pcm)
    if not samples:
        return 0.0
    stride = max(1, len(samples) // _MAX_RMS_SAMPLES)
    if stride > 1:
        samples = samples[::stride]
    total = 0
    for s in samples:
        total += s if s >= 0 else -s
    mean_abs = total / len(samples)
    return round(mean_abs / 32768.0, 6)


@dataclass
class TurnFeatures:
    """Raw measurements for a single participant turn."""

    transcript_sequence: int
    response_latency_ms: Optional[int] = None
    voiced_ms: Optional[int] = None
    word_count: Optional[int] = None
    char_count: Optional[int] = None
    speech_rate_wpm: Optional[float] = None
    filler_count: Optional[int] = None
    rms_energy: Optional[float] = None

    @classmethod
    def from_turn(
        cls,
        *,
        transcript_sequence: int,
        text: str,
        language: Optional[str],
        response_latency_ms: Optional[int],
        voiced_ms: Optional[int],
        pcm: bytes = b"",
        modality: str = "voice",
    ) -> "TurnFeatures":
        words = word_count(text)
        chars = len(text or "")
        fillers = count_fillers(text, language, modality)
        rate: Optional[float] = None
        if voiced_ms and voiced_ms > 0 and words:
            rate = round(words / (voiced_ms / 60000.0), 1)
        return cls(
            transcript_sequence=transcript_sequence,
            response_latency_ms=response_latency_ms,
            voiced_ms=voiced_ms,
            word_count=words,
            char_count=chars,
            speech_rate_wpm=rate,
            filler_count=fillers,
            rms_energy=rms_energy(pcm) if pcm else None,
        )

    def to_dict(self) -> dict:
        return asdict(self)
