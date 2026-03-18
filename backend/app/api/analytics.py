"""
OASIS — Study-level analytics endpoint.

Provides aggregate statistics across all agents in a study.
Uses two aggregated queries (session stats + utterance counts) instead of
N+1 per-agent loops, so performance stays constant regardless of agent count.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent import Agent
from app.models.session import Session, SessionStatus, TranscriptEntry
from app.models.study import Study
from app.schemas.analytics import AgentStats, StudyAnalytics

router = APIRouter(
    prefix="/studies/{study_id}/analytics",
    tags=["analytics"],
)


@router.get("", response_model=StudyAnalytics)
async def get_study_analytics(
    study_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get aggregate analytics for an entire study, broken down by agent.
    """
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    # Fetch all agents for this study (light query — names + ids only)
    agent_result = await db.execute(
        select(Agent.id, Agent.name).where(Agent.study_id == study_id)
    )
    agents_map: dict[UUID, str] = {row.id: row.name for row in agent_result.all()}

    if not agents_map:
        return StudyAnalytics(
            study_id=str(study_id),
            total_sessions=0,
            completed_sessions=0,
            error_sessions=0,
            timed_out_sessions=0,
            active_sessions=0,
            avg_duration_seconds=None,
            total_utterances=0,
            completion_rate=0.0,
            agents=[],
        )

    agent_ids = list(agents_map.keys())

    # ── Single aggregated query: session stats grouped by agent_id ──
    session_stats = await db.execute(
        select(
            Session.agent_id,
            func.count(Session.id).label("total"),
            func.count(case((Session.status == SessionStatus.COMPLETED, 1))).label("completed"),
            func.count(case((Session.status == SessionStatus.ERROR, 1))).label("errors"),
            func.count(case((Session.status == SessionStatus.TIMED_OUT, 1))).label("timed_out"),
            func.count(case((Session.status == SessionStatus.ACTIVE, 1))).label("active"),
            func.avg(Session.duration_seconds).label("avg_duration"),
        )
        .where(Session.agent_id.in_(agent_ids))
        .group_by(Session.agent_id)
    )
    stats_by_agent: dict[UUID, any] = {row.agent_id: row for row in session_stats.all()}

    # ── Single aggregated query: utterance counts grouped by agent_id ──
    utterance_stats = await db.execute(
        select(
            Session.agent_id,
            func.count(TranscriptEntry.id).label("utterances"),
        )
        .join(Session, TranscriptEntry.session_id == Session.id)
        .where(Session.agent_id.in_(agent_ids))
        .group_by(Session.agent_id)
    )
    utterances_by_agent: dict[UUID, int] = {
        row.agent_id: row.utterances for row in utterance_stats.all()
    }

    # ── Build per-agent stats and study totals in one pass ──
    agent_stats_list: list[AgentStats] = []
    study_total = 0
    study_completed = 0
    study_errors = 0
    study_timed_out = 0
    study_active = 0
    study_durations: list[float] = []
    study_utterances = 0

    for agent_id, agent_name in agents_map.items():
        row = stats_by_agent.get(agent_id)
        agent_utterances = utterances_by_agent.get(agent_id, 0)

        total = row.total if row else 0
        completed = row.completed if row else 0
        errors = row.errors if row else 0
        timed_out = row.timed_out if row else 0
        active = row.active if row else 0
        avg_dur = row.avg_duration if row else None
        finished = completed + errors + timed_out
        completion_rate = (completed / finished * 100) if finished > 0 else 0.0

        agent_stats_list.append(AgentStats(
            agent_id=str(agent_id),
            agent_name=agent_name,
            total_sessions=total,
            completed_sessions=completed,
            error_sessions=errors,
            timed_out_sessions=timed_out,
            active_sessions=active,
            avg_duration_seconds=round(avg_dur, 1) if avg_dur else None,
            total_utterances=agent_utterances,
            completion_rate=round(completion_rate, 1),
        ))

        study_total += total
        study_completed += completed
        study_errors += errors
        study_timed_out += timed_out
        study_active += active
        study_utterances += agent_utterances
        if avg_dur:
            study_durations.append(float(avg_dur))

    study_finished = study_completed + study_errors + study_timed_out
    study_completion_rate = (study_completed / study_finished * 100) if study_finished > 0 else 0.0
    study_avg_duration = (
        round(sum(study_durations) / len(study_durations), 1)
        if study_durations
        else None
    )

    return StudyAnalytics(
        study_id=str(study_id),
        total_sessions=study_total,
        completed_sessions=study_completed,
        error_sessions=study_errors,
        timed_out_sessions=study_timed_out,
        active_sessions=study_active,
        avg_duration_seconds=study_avg_duration,
        total_utterances=study_utterances,
        completion_rate=round(study_completion_rate, 1),
        agents=agent_stats_list,
    )
