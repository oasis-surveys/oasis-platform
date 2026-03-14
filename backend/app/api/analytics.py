"""
SURVEYOR — Study-level analytics endpoint.

Provides aggregate statistics across all agents in a study.
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

    # Fetch all agents for this study
    agent_result = await db.execute(
        select(Agent).where(Agent.study_id == study_id)
    )
    agents_list = agent_result.scalars().all()

    agent_stats: list[AgentStats] = []
    study_total = 0
    study_completed = 0
    study_errors = 0
    study_timed_out = 0
    study_active = 0
    study_durations: list[float] = []
    study_utterances = 0

    for agent in agents_list:
        # Session stats per agent
        result = await db.execute(
            select(
                func.count(Session.id).label("total"),
                func.count(case((Session.status == SessionStatus.COMPLETED, 1))).label("completed"),
                func.count(case((Session.status == SessionStatus.ERROR, 1))).label("errors"),
                func.count(case((Session.status == SessionStatus.TIMED_OUT, 1))).label("timed_out"),
                func.count(case((Session.status == SessionStatus.ACTIVE, 1))).label("active"),
                func.avg(Session.duration_seconds).label("avg_duration"),
            )
            .where(Session.agent_id == agent.id)
        )
        row = result.one()

        # Utterance count per agent
        utterance_result = await db.execute(
            select(func.count(TranscriptEntry.id))
            .join(Session, TranscriptEntry.session_id == Session.id)
            .where(Session.agent_id == agent.id)
        )
        agent_utterances = utterance_result.scalar() or 0

        total = row.total or 0
        completed = row.completed or 0
        errors = row.errors or 0
        timed_out = row.timed_out or 0
        active = row.active or 0
        finished = completed + errors + timed_out
        completion_rate = (completed / finished * 100) if finished > 0 else 0.0

        agent_stats.append(AgentStats(
            agent_id=str(agent.id),
            agent_name=agent.name,
            total_sessions=total,
            completed_sessions=completed,
            error_sessions=errors,
            timed_out_sessions=timed_out,
            active_sessions=active,
            avg_duration_seconds=round(row.avg_duration, 1) if row.avg_duration else None,
            total_utterances=agent_utterances,
            completion_rate=round(completion_rate, 1),
        ))

        # Accumulate study totals
        study_total += total
        study_completed += completed
        study_errors += errors
        study_timed_out += timed_out
        study_active += active
        study_utterances += agent_utterances
        if row.avg_duration:
            study_durations.append(float(row.avg_duration))

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
        agents=agent_stats,
    )
