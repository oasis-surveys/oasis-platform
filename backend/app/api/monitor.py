"""
OASIS — Real-time transcript monitor WebSocket.

Researchers connect to:
    ws://host/ws/monitor/{session_id}?token=<jwt>

When ``AUTH_ENABLED`` is true the connection is rejected (with WS close code
4401) unless ``token`` is a valid JWT issued by ``/api/auth/login``. Browser
WebSocket APIs cannot send custom headers, so we accept the JWT in a query
parameter — the same pattern used by `wss://` deployments at large.

The endpoint streams transcript entries as they are logged by the pipeline.
It also sends the existing transcript first so the researcher sees
the full conversation up to this point.
"""

from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth import verify_token
from app.config import settings
from app.database import async_session_factory
from app.models.session import Session, SessionStatus, TranscriptEntry
from app.realtime import subscribe_transcript

router = APIRouter()


@router.websocket("/ws/monitor/{session_id}")
async def monitor_ws(
    websocket: WebSocket,
    session_id: str,
    token: str | None = None,
):
    """
    Real-time transcript monitor for researchers.

    1. Sends the full existing transcript (backfill)
    2. Streams new entries via Redis pub/sub as they arrive
    3. Sends a 'session_ended' event when the session finishes
    """
    # ── Auth check (before accept so we can reject with a close code) ──
    if settings.auth_enabled:
        payload = verify_token(token) if token else None
        if not payload:
            # Per RFC 6455, custom close codes 4000-4999 are application defined.
            # 4401 is the de-facto convention for "WebSocket Unauthorized".
            await websocket.close(code=4401)
            logger.warning(
                f"Monitor rejected for session {session_id}: missing/invalid token"
            )
            return

    await websocket.accept()
    logger.info(f"Monitor connected for session {session_id}")

    try:
        # ── 1. Backfill existing transcript ─────────────────────────
        async with async_session_factory() as db:
            result = await db.execute(
                select(Session)
                .where(Session.id == UUID(session_id))
                .options(selectinload(Session.entries))
            )
            session = result.scalar_one_or_none()

            if not session:
                await websocket.send_json({"type": "error", "message": "Session not found"})
                await websocket.close(code=4004)
                return

            # Send session metadata
            await websocket.send_json({
                "type": "session_info",
                "session_id": str(session.id),
                "agent_id": str(session.agent_id),
                "status": session.status.value,
                "created_at": session.created_at.isoformat(),
            })

            # Send existing transcript entries
            for entry in session.entries:
                await websocket.send_json({
                    "type": "transcript",
                    "role": entry.role.value,
                    "content": entry.content,
                    "sequence": entry.sequence,
                    "spoken_at": entry.spoken_at.isoformat(),
                })

            is_active = session.status == SessionStatus.ACTIVE

        if not is_active:
            # Session already finished — send end signal and close
            await websocket.send_json({
                "type": "session_ended",
                "status": session.status.value,
            })
            await websocket.close()
            return

        # ── 2. Stream live updates via Redis pub/sub ────────────────
        async for event in subscribe_transcript(session_id):
            await websocket.send_json(event)

            # If the session ended, break out of the loop
            if event.get("type") == "session_ended":
                break

    except WebSocketDisconnect:
        logger.info(f"Monitor disconnected for session {session_id}")
    except Exception as exc:
        logger.exception(f"Monitor error for session {session_id}: {exc}")
    finally:
        logger.info(f"Monitor WebSocket closed for session {session_id}")
