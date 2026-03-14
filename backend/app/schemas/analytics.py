"""Pydantic schemas for analytics responses."""

from pydantic import BaseModel


class AgentStats(BaseModel):
    """Aggregate stats for a single agent."""
    agent_id: str
    agent_name: str
    total_sessions: int
    completed_sessions: int
    error_sessions: int
    timed_out_sessions: int
    active_sessions: int
    avg_duration_seconds: float | None
    total_utterances: int
    completion_rate: float  # completed / (completed + error + timed_out)


class StudyAnalytics(BaseModel):
    """Aggregate stats for an entire study across all its agents."""
    study_id: str
    total_sessions: int
    completed_sessions: int
    error_sessions: int
    timed_out_sessions: int
    active_sessions: int
    avg_duration_seconds: float | None
    total_utterances: int
    completion_rate: float
    agents: list[AgentStats]
