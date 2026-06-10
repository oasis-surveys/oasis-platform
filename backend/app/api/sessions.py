"""
OASIS — Session read, filter, and export endpoints.

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
from app.models.engagement import AdaptiveAction, EngagementEvent, EngagementTurn
from app.models.session import Session, SessionStatus, TranscriptEntry
from app.realtime import publish_transcript_event
from app.audio.storage import build_session_prefix, get_audio_storage
from app.schemas.session import (
    AdaptiveActionRead,
    EngagementEventRead,
    EngagementSummaryRead,
    EngagementTurnRead,
    SessionAudioManifestRead,
    SessionDetailRead,
    SessionRead,
    AudioTurnRead,
)

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

_EXPORT_BATCH_SIZE = 100  # Process sessions in batches to limit memory


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

    Columns: session_id, participant_id, status, duration_seconds,
             created_at, ended_at, entry_sequence, role, content, spoken_at

    Uses batched fetching to avoid loading all sessions into memory at once.
    """
    await _get_agent_or_404(study_id, agent_id, db)

    # First pass: get matching session IDs only (lightweight)
    id_stmt = (
        select(Session.id)
        .where(Session.agent_id == agent_id)
        .order_by(Session.created_at.desc())
    )
    id_stmt = _apply_filters(id_stmt, status, date_from, date_to, session_ids)
    id_result = await db.execute(id_stmt)
    all_ids = [row[0] for row in id_result.all()]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "session_id",
        "participant_id",
        "session_status",
        "duration_seconds",
        "session_created_at",
        "session_ended_at",
        "entry_sequence",
        "role",
        "content",
        "spoken_at",
        "engagement_score",
        "engagement_label",
        "response_latency_ms",
        "word_count",
        "speech_rate_wpm",
        "filler_count",
        "engagement_events",
        "adaptive_actions",
    ])

    # Process in batches
    for i in range(0, len(all_ids), _EXPORT_BATCH_SIZE):
        batch_ids = all_ids[i : i + _EXPORT_BATCH_SIZE]
        batch_result = await db.execute(
            select(Session)
            .where(Session.id.in_(batch_ids))
            .options(
                selectinload(Session.entries),
                selectinload(Session.engagement_turns),
                selectinload(Session.engagement_events),
                selectinload(Session.adaptive_actions),
            )
            .order_by(Session.created_at.desc())
        )
        batch_sessions = batch_result.scalars().all()

        for session in batch_sessions:
            # Engagement rows key off the user transcript sequence.
            eng_by_seq = {
                e.transcript_sequence: e for e in session.engagement_turns
            }
            # Events grouped by the turn that triggered them.
            events_by_seq: dict[int, list[str]] = {}
            for ev in session.engagement_events:
                if ev.transcript_sequence is not None:
                    events_by_seq.setdefault(ev.transcript_sequence, []).append(
                        ev.event_type
                    )
            # Adaptive actions grouped by the turn that triggered them.
            actions_by_seq: dict[int, list[str]] = {}
            for act in session.adaptive_actions:
                if act.transcript_sequence is not None:
                    applied = (act.detail or {}).get("applied")
                    tag = f"{act.action}({act.mode}{'' if applied else ':not_applied'})"
                    actions_by_seq.setdefault(act.transcript_sequence, []).append(tag)
            if not session.entries:
                writer.writerow([
                    str(session.id),
                    session.participant_id or "",
                    session.status.value,
                    session.duration_seconds,
                    session.created_at.isoformat(),
                    session.ended_at.isoformat() if session.ended_at else "",
                    "", "", "", "",
                    "", "", "", "", "", "", "", "",
                ])
            else:
                for entry in sorted(session.entries, key=lambda e: e.sequence):
                    is_user = entry.role.value == "user"
                    eng = eng_by_seq.get(entry.sequence) if is_user else None
                    events = events_by_seq.get(entry.sequence, []) if is_user else []
                    actions = actions_by_seq.get(entry.sequence, []) if is_user else []
                    writer.writerow([
                        str(session.id),
                        session.participant_id or "",
                        session.status.value,
                        session.duration_seconds,
                        session.created_at.isoformat(),
                        session.ended_at.isoformat() if session.ended_at else "",
                        entry.sequence,
                        entry.role.value,
                        entry.content,
                        entry.spoken_at.isoformat(),
                        eng.score if eng else "",
                        eng.label if eng else "",
                        eng.response_latency_ms if eng else "",
                        eng.word_count if eng else "",
                        eng.speech_rate_wpm if eng else "",
                        eng.filler_count if eng else "",
                        ", ".join(events),
                        ", ".join(actions),
                    ])

        # Expire loaded objects to free memory between batches
        db.expire_all()

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

    Uses batched fetching to avoid loading all sessions into memory at once.
    """
    await _get_agent_or_404(study_id, agent_id, db)

    # First pass: get matching session IDs only (lightweight)
    id_stmt = (
        select(Session.id)
        .where(Session.agent_id == agent_id)
        .order_by(Session.created_at.desc())
    )
    id_stmt = _apply_filters(id_stmt, status, date_from, date_to, session_ids)
    id_result = await db.execute(id_stmt)
    all_ids = [row[0] for row in id_result.all()]

    data = []

    # Process in batches
    for i in range(0, len(all_ids), _EXPORT_BATCH_SIZE):
        batch_ids = all_ids[i : i + _EXPORT_BATCH_SIZE]
        batch_result = await db.execute(
            select(Session)
            .where(Session.id.in_(batch_ids))
            .options(
                selectinload(Session.entries),
                selectinload(Session.engagement_turns),
                selectinload(Session.engagement_events),
                selectinload(Session.adaptive_actions),
            )
            .order_by(Session.created_at.desc())
        )
        batch_sessions = batch_result.scalars().all()

        for session in batch_sessions:
            engagement_rows = sorted(
                session.engagement_turns, key=lambda e: e.transcript_sequence
            )
            engagement_events = list(session.engagement_events)
            adaptive_actions = list(session.adaptive_actions)
            session_data = {
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
                    for entry in sorted(session.entries, key=lambda e: e.sequence)
                ],
            }
            if engagement_rows:
                summary = _summarize_engagement(
                    session.id, engagement_rows, engagement_events
                )
                session_data["engagement"] = {
                    "turn_count": summary.turn_count,
                    "average_score": summary.average_score,
                    "label": summary.label,
                    "average_latency_ms": summary.average_latency_ms,
                    "average_words": summary.average_words,
                    "low_engagement_turns": summary.low_engagement_turns,
                    "turns": [t.model_dump() for t in summary.turns],
                    "events": [e.model_dump() for e in summary.events],
                }
            if session.adaptive_active or adaptive_actions:
                session_data["adaptive"] = {
                    "active": bool(session.adaptive_active),
                    "actions": [
                        {
                            "transcript_sequence": a.transcript_sequence,
                            "trigger": a.trigger,
                            "action": a.action,
                            "mode": a.mode,
                            "detail": a.detail,
                            "created_at": a.created_at.isoformat(),
                        }
                        for a in adaptive_actions
                    ],
                }
            data.append(session_data)

        # Expire loaded objects to free memory between batches
        db.expire_all()

    json_content = json.dumps(data, indent=2, ensure_ascii=False)
    return Response(
        content=json_content,
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=sessions_{agent_id}.json",
        },
    )


def _session_audio_prefix(session: Session, agent: Agent) -> str:
    return build_session_prefix(
        study_id=agent.study_id,
        agent_id=agent.id,
        participant_id=session.participant_id,
        session_id=session.id,
    )


async def _get_session_with_agent(
    study_id: UUID, agent_id: UUID, session_id: UUID, db: AsyncSession
) -> tuple[Session, Agent]:
    agent = await _get_agent_or_404(study_id, agent_id, db)
    session = await db.get(Session, session_id)
    if not session or session.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Session not found")
    return session, agent


# ── Session audio (voice web recordings) ───────────────────────────────────────

@router.get("/{session_id}/audio", response_model=SessionAudioManifestRead)
async def get_session_audio_manifest(
    study_id: UUID,
    agent_id: UUID,
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return manifest of session audio files for a recorded session."""
    session, agent = await _get_session_with_agent(study_id, agent_id, session_id, db)
    if not session.audio_recording_enabled:
        raise HTTPException(status_code=404, detail="Audio recording was not enabled for this session")

    storage = await get_audio_storage()
    if not storage:
        raise HTTPException(status_code=503, detail="Audio storage is not configured on this server")

    prefix = _session_audio_prefix(session, agent)
    try:
        raw = await storage.read_bytes(f"{prefix}/manifest.json")
        manifest = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=404, detail="Audio manifest not found")

    turns = [
        AudioTurnRead(
            sequence=t["sequence"],
            role=t["role"],
            filename=t["filename"],
            duration_ms=t.get("duration_ms"),
            content_preview=t.get("content_preview"),
        )
        for t in manifest.get("turns", [])
    ]
    return SessionAudioManifestRead(
        session_id=session.id,
        storage_uri=session.audio_storage_uri,
        recording_status=session.audio_recording_status,
        turns=turns,
    )


@router.get("/{session_id}/audio/{filename}")
async def download_session_audio_turn(
    study_id: UUID,
    agent_id: UUID,
    session_id: UUID,
    filename: str,
    db: AsyncSession = Depends(get_db),
):
    """Download a session WAV (e.g. session_user.wav)."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    session, agent = await _get_session_with_agent(study_id, agent_id, session_id, db)
    if not session.audio_recording_enabled:
        raise HTTPException(status_code=404, detail="Audio recording was not enabled for this session")

    storage = await get_audio_storage()
    if not storage:
        raise HTTPException(status_code=503, detail="Audio storage is not configured on this server")

    prefix = _session_audio_prefix(session, agent)
    key = f"{prefix}/{filename}"
    try:
        data = await storage.read_bytes(key)
    except Exception:
        raise HTTPException(status_code=404, detail="Audio file not found")

    return Response(
        content=data,
        media_type="audio/wav",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Session engagement metrics ──────────────────────────────────────────────

def _summarize_engagement(
    session_id: UUID,
    rows: list[EngagementTurn],
    events: list[EngagementEvent] | None = None,
    adaptive_actions: list["AdaptiveAction"] | None = None,
    adaptive_active: bool = False,
) -> EngagementSummaryRead:
    turns = [
        EngagementTurnRead(
            transcript_sequence=r.transcript_sequence,
            response_latency_ms=r.response_latency_ms,
            voiced_ms=r.voiced_ms,
            word_count=r.word_count,
            char_count=r.char_count,
            speech_rate_wpm=r.speech_rate_wpm,
            filler_count=r.filler_count,
            rms_energy=r.rms_energy,
            score=r.score,
            label=r.label,
            flags=list((r.extras or {}).get("flags", [])),
        )
        for r in rows
    ]

    scores = [r.score for r in rows if r.score is not None]
    latencies = [r.response_latency_ms for r in rows if r.response_latency_ms is not None]
    words = [r.word_count for r in rows if r.word_count is not None]
    avg_score = round(sum(scores) / len(scores), 3) if scores else None

    if avg_score is None:
        label = None
    elif avg_score < 0.34:
        label = "low"
    elif avg_score >= 0.67:
        label = "high"
    else:
        label = "medium"

    return EngagementSummaryRead(
        session_id=session_id,
        turn_count=len(rows),
        average_score=avg_score,
        label=label,
        average_latency_ms=int(sum(latencies) / len(latencies)) if latencies else None,
        average_words=round(sum(words) / len(words), 1) if words else None,
        low_engagement_turns=sum(1 for r in rows if r.label == "low"),
        turns=turns,
        events=[
            EngagementEventRead(
                transcript_sequence=e.transcript_sequence,
                event_type=e.event_type,
                score_at_event=e.score_at_event,
            )
            for e in (events or [])
        ],
        adaptive_active=adaptive_active,
        adaptive_actions=[
            AdaptiveActionRead(
                transcript_sequence=a.transcript_sequence,
                trigger=a.trigger,
                action=a.action,
                mode=a.mode,
                detail=a.detail,
                created_at=a.created_at,
            )
            for a in (adaptive_actions or [])
        ],
    )


@router.get("/{session_id}/engagement", response_model=EngagementSummaryRead)
async def get_session_engagement(
    study_id: UUID,
    agent_id: UUID,
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return per-turn engagement metrics and a session summary."""
    session, _agent = await _get_session_with_agent(study_id, agent_id, session_id, db)
    result = await db.execute(
        select(EngagementTurn)
        .where(EngagementTurn.session_id == session.id)
        .order_by(EngagementTurn.transcript_sequence)
    )
    rows = list(result.scalars().all())
    ev_result = await db.execute(
        select(EngagementEvent)
        .where(EngagementEvent.session_id == session.id)
        .order_by(EngagementEvent.created_at)
    )
    events = list(ev_result.scalars().all())
    act_result = await db.execute(
        select(AdaptiveAction)
        .where(AdaptiveAction.session_id == session.id)
        .order_by(AdaptiveAction.created_at)
    )
    actions = list(act_result.scalars().all())
    return _summarize_engagement(
        session.id,
        rows,
        events,
        adaptive_actions=actions,
        adaptive_active=bool(session.adaptive_active),
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
