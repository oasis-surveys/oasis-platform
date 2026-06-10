"""
OASIS — Engagement metrics (Phase 1, observational only).

Computes lightweight per-turn signals from a participant's voice turns
(latency, length, speech rate, fillers, energy) and a transparent
rule-based score. Nothing here changes the interview; it only measures.
"""

from app.engagement.adaptive import (
    ACTION_CATALOG,
    AdaptivePolicy,
    AdaptivePolicyEngine,
    AdaptiveSignals,
    ResolvedAction,
)
from app.engagement.events import EngagementEventResult, EventDetector
from app.engagement.features import TurnFeatures, count_fillers, rms_energy
from app.engagement.scorer import RuleBasedScorer, ScorerConfig, TurnScore

__all__ = [
    "TurnFeatures",
    "count_fillers",
    "rms_energy",
    "RuleBasedScorer",
    "ScorerConfig",
    "TurnScore",
    "EventDetector",
    "EngagementEventResult",
    "ACTION_CATALOG",
    "AdaptivePolicy",
    "AdaptivePolicyEngine",
    "AdaptiveSignals",
    "ResolvedAction",
]
