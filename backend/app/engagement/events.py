"""
OASIS — Rolling-window engagement event detection (Phase 2).

Stateful detector fed one turn label at a time. Emits discrete events when
the recent window of turns crosses a condition. Each event fires once when its
condition first becomes true and re-arms only after the condition clears, so a
session does not get one row per turn for a sustained state.

Observe-only: events are recorded and exported; they do not change the
interview.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from app.engagement.scorer import ScorerConfig

SUSTAINED_DISENGAGEMENT = "sustained_disengagement"
POSITIVE_ENGAGEMENT_STREAK = "positive_engagement_streak"
RECOVERY_AFTER_DIP = "recovery_after_dip"


@dataclass
class EngagementEventResult:
    event_type: str
    payload: dict


class EventDetector:
    def __init__(self, config: ScorerConfig | None = None):
        cfg = config or ScorerConfig()
        self._window = max(2, cfg.window_size)
        self._labels: deque[str] = deque(maxlen=self._window)
        self._disengage_armed = True
        self._streak_armed = True
        self._dip_seen = False

    def observe(self, label: str) -> list[EngagementEventResult]:
        """Feed one turn label; return any events triggered by this turn."""
        events: list[EngagementEventResult] = []
        self._labels.append(label)
        window = list(self._labels)

        full = len(self._labels) == self._window

        # Sustained disengagement: a full window of consecutive low turns.
        if full and all(lbl == "low" for lbl in window):
            if self._disengage_armed:
                events.append(
                    EngagementEventResult(
                        SUSTAINED_DISENGAGEMENT, {"window": window}
                    )
                )
                self._disengage_armed = False
        if label != "low":
            self._disengage_armed = True

        # Positive engagement streak: a full window of consecutive high turns.
        if full and all(lbl == "high" for lbl in window):
            if self._streak_armed:
                events.append(
                    EngagementEventResult(
                        POSITIVE_ENGAGEMENT_STREAK, {"window": window}
                    )
                )
                self._streak_armed = False
        if label != "high":
            self._streak_armed = True

        # Recovery after a dip: a high turn following at least one recent low.
        if label == "low":
            self._dip_seen = True
        elif label == "high" and self._dip_seen:
            events.append(EngagementEventResult(RECOVERY_AFTER_DIP, {}))
            self._dip_seen = False

        return events
