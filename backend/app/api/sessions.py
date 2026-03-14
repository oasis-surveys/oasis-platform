"""
SURVEYOR — Session read, filter, and export endpoints.

Sessions are created automatically when a participant connects via WebSocket.
These endpoints let researchers view, filter, and export transcripts.
"""

import csv
import io
import json
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from loguru import logger
from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.agent import Agent
from app.models.session import Session, SessionStatus, TranscriptEntry
from app.realtime import publish_transcript_event
from app.schemas.session import SessionDetailRead, SessionRead

router = APIRouter(
    prefix="/studies/{study_id}/agents/{agent_id}/sessions",
    tags=["sessions"],
)


async def _get_agent_or_404(
    study_id: UUID, agent_id: UUID, db: AsyncSession
) -> Agent:
    agent = await db.get(Agent, agent_id)
    if not agent or agent.study_id != study_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _apply_filters(stmt, status, date_from, date_to, session_ids=None):
    """Apply common query filters."""
    if status:
        try:
            stmt = stmt.where(Session.status == SessionStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    if date_from:
        stmt = stmt.where(Session.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Session.created_at <= date_to)
    if session_ids:
        try:
            ids = [UUID(sid.strip()) for sid in session_ids.split(",") if sid.strip()]
            if ids:
                stmt = stmt.where(Session.id.in_(ids))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid session_ids format")
    return stmt


# ──────────────────────────────────────────────────────────────────────────────
# IMPORTANT: Fixed-path routes MUST be defined BEFORE /{session_id}
# so FastAPI doesn't try to parse "export" or "stats" as a UUID.
# ──────────────────────────────────────────────────────────────────────────────


# ── Session statistics (per agent) ───────────────────────────────────────────

@router.get("/stats/summary")
async def session_stats(
    study_id: UUID,
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get aggregate statistics for all sessions under an agent.
    """
    await _get_agent_or_404(study_id, agent_id, db)

    result = await db.execute(
        select(
            func.count(Session.id).label("total"),
            func.count(case((Session.status == SessionStatus.COMPLETED, 1))).label("completed"),
            func.count(case((Session.status == SessionStatus.ERROR, 1))).label("errors"),
            func.count(case((Session.status == SessionStatus.TIMED_OUT, 1))).label("timed_out"),
            func.count(case((Session.status == SessionStatus.ACTIVE, 1))).label("active"),
            func.avg(Session.duration_seconds).label("avg_duration"),
        )
        .where(Session.agent_id == agent_id)
    )
    row = result.one()

    # Count total utterances
    utterance_result = await db.execute(
        select(func.count(TranscriptEntry.id))
        .join(Session, TranscriptEntry.session_id == Session.id)
        .where(Session.agent_id == agent_id)
    )
    total_utterances = utterance_result.scalar() or 0

    total = row.total or 0
    completed = row.completed or 0
    errors = row.errors or 0
    timed_out = row.timed_out or 0
    finished = completed + errors + timed_out
    completion_rate = (completed / finished * 100) if finished > 0 else 0.0

    return {
        "total_sessions": total,
        "completed_sessions": completed,
        "error_sessions": errors,
        "timed_out_sessions": timed_out,
        "active_sessions": row.active or 0,
        "avg_duration_seconds": round(row.avg_duration, 1) if row.avg_duration else None,
        "total_utterances": total_utterances,
        "completion_rate": round(completion_rate, 1),
    }


# ── Export transcripts ────────────────────────────────────────────────────────

@router.get("/export/csv")
async def export_sessions_csv(
    study_id: UUID,
    agent_id: UUID,
    status: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    session_ids: Optional[str] = Query(None, description="Comma-separated session UUIDs to export"),
    db: AsyncSession = Depends(get_db),
):
    """
    Export all sessions and transcripts as a CSV file.

    Columns: session_id, status, duration_seconds, created_at, ended_at,
             entry_sequence, role, content, spoken_at
    """
    await _get_agent_or_404(study_id, agent_id, db)

    stmt = (
        select(Session)
        .where(Session.agent_id == agent_id)
        .options(selectinload(Session.entries))
        .order_by(Session.created_at.desc())
    )
    stmt = _apply_filters(stmt, status, date_from, date_to, session_ids)

    result = await db.execute(stmt)
    all_sessions = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "session_id",
        "session_status",
        "duration_seconds",
        "session_created_at",
        "session_ended_at",
        "entry_sequence",
        "role",
        "content",
        "spoken_at",
    ])

    for session in all_sessions:
        if not session.entries:
            writer.writerow([
                str(session.id),
                session.status.value,
                session.duration_seconds,
                session.created_at.isoformat(),
                session.ended_at.isoformat() if session.ended_at else "",
                "", "", "", "",
            ])
        else:
            for entry in session.entries:
                writer.writerow([
                    str(session.id),
                    session.status.value,
                    session.duration_seconds,
                    session.created_at.isoformat(),
                    session.ended_at.isoformat() if session.ended_at else "",
                    entry.sequence,
                    entry.role.value,
                    entry.content,
                    entry.spoken_at.isoformat(),
                ])

    csv_content = output.getvalue()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=sessions_{agent_id}.csv",
        },
    )


@router.get("/export/json")
async def export_sessions_json(
    study_id: UUID,
    agent_id: UUID,
    status: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    session_ids: Optional[str] = Query(None, description="Comma-separated session UUIDs to export"),
    db: AsyncSession = Depends(get_db),
):
    """
    Export all sessions and transcripts as a JSON file.
    """
    await _get_agent_or_404(study_id, agent_id, db)

    stmt = (
        select(Session)
        .where(Session.agent_id == agent_id)
        .options(selectinload(Session.entries))
        .order_by(Session.created_at.desc())
    )
    stmt = _apply_filters(stmt, status, date_from, date_to, session_ids)

    result = await db.execute(stmt)
    all_sessions = result.scalars().all()

    data = []
    for session in all_sessions:
        data.append({
            "session_id": str(session.id),
            "status": session.status.value,
            "duration_seconds": session.duration_seconds,
            "total_tokens": session.total_tokens,
            "participant_id": session.participant_id,
            "created_at": session.created_at.isoformat(),
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "transcript": [
                {
                    "sequence": entry.sequence,
                    "role": entry.role.value,
                    "content": entry.content,
                    "spoken_at": entry.spoken_at.isoformat(),
                    "prompt_tokens": entry.prompt_tokens,
                    "completion_tokens": entry.completion_tokens,
                }
                for entry in session.entries
            ],
        })

    json_content = json.dumps(data, indent=2, ensure_ascii=False)
    return Response(
        content=json_content,
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=sessions_{agent_id}.json",
        },
    )


# ── List sessions with filtering ─────────────────────────────────────────────

@router.get("", response_model=list[SessionRead])
async def list_sessions(
    study_id: UUID,
    agent_id: UUID,
    status: Optional[str] = Query(None, description="Filter by status (active, completed, timed_out, error)"),
    date_from: Optional[datetime] = Query(None, description="Filter sessions created after this datetime"),
    date_to: Optional[datetime] = Query(None, description="Filter sessions created before this datetime"),
    sort_by: Optional[str] = Query("created_at", description="Sort field (created_at, duration_seconds, status)"),
    sort_order: Optional[str] = Query("desc", description="Sort order (asc, desc)"),
    db: AsyncSession = Depends(get_db),
):
    """List all sessions for an agent with optional filtering and sorting."""
    await _get_agent_or_404(study_id, agent_id, db)

    stmt = select(Session).where(Session.agent_id == agent_id)
    stmt = _apply_filters(stmt, status, date_from, date_to)

    # Apply sorting
    sort_column = {
        "created_at": Session.created_at,
        "duration_seconds": Session.duration_seconds,
        "status": Session.status,
    }.get(sort_by, Session.created_at)

    if sort_order == "asc":
        stmt = stmt.order_by(sort_column.asc())
    else:
        stmt = stmt.order_by(sort_column.desc())

    result = await db.execute(stmt)
    return result.scalars().all()


# ── Get single session with transcript ────────────────────────────────────────

@router.get("/{session_id}", response_model=SessionDetailRead)
async def get_session(
    study_id: UUID,
    agent_id: UUID,
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a session with its full transcript."""
    await _get_agent_or_404(study_id, agent_id, db)
    result = await db.execute(
        select(Session)
        .where(Session.id == session_id, Session.agent_id == agent_id)
        .options(selectinload(Session.entries))
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/{session_id}/terminate", status_code=204)
async def terminate_session(
    study_id: UUID,
    agent_id: UUID,
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Administratively terminate an active session.

    Marks the session as completed in the database and broadcasts a
    session_ended event so the live monitor and interview pipeline shut down.
    The interview WebSocket pipeline will close once it detects the session
    is no longer active (via the pipeline's EndFrame / disconnect handling).
    """
    await _get_agent_or_404(study_id, agent_id, db)
    session = await db.get(Session, session_id)
    if not session or session.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != SessionStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Session is not active")

    now = datetime.now(timezone.utc)
    start = session.created_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    duration = (now - start).total_seconds()

    session.status = SessionStatus.COMPLETED
    session.ended_at = now
    session.duration_seconds = duration
    await db.commit()

    # Notify live monitors that the session ended
    await publish_transcript_event(
        str(session_id),
        {
            "type": "session_ended",
            "status": SessionStatus.COMPLETED.value,
            "duration_seconds": round(duration, 1),
        },
    )

    logger.info(
        f"Session {session_id} terminated by admin after {duration:.1f}s"
    )
