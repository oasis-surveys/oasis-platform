"""
SURVEYOR — WebSocket endpoint for live interviews.

When a participant opens the widget, the frontend connects to:
    ws://host/ws/interview/{widget_key}?pid=<optional>

The endpoint:
1. Looks up the agent by its unique widget_key
2. Resolves participant_id (random / predefined / input)
3. Creates a new Session row
4. Boots a Pipecat pipeline that runs for the duration of the call
5. Updates the session status when the call ends
"""

import asyncio
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from loguru import logger
from sqlalchemy import select

from app.database import async_session_factory
from app.models.agent import Agent, AgentStatus, ParticipantIdMode, ParticipantIdentifier
from app.models.session import Session, SessionStatus
from app.realtime import publish_transcript_event

router = APIRouter()

# Maximum pipeline runtime (seconds).  Prevents zombie pipelines that never
# end even after a disconnect handler fires.
_MAX_PIPELINE_SECONDS = 7200  # 2 hours absolute ceiling


@router.websocket("/ws/interview/{widget_key}")
async def interview_ws(
    websocket: WebSocket,
    widget_key: str,
    pid: str | None = Query(None),
):
    """
    Main voice-interview WebSocket endpoint.

    The browser widget connects here and streams raw PCM audio
    via the Pipecat protobuf serialiser.
    """
    await websocket.accept()

    # ── 1. Resolve agent by widget_key ─────────────────────────────
    async with async_session_factory() as db:
        result = await db.execute(
            select(Agent).where(
                Agent.widget_key == widget_key,
                Agent.status == AgentStatus.ACTIVE.value,
            )
        )
        agent = result.scalar_one_or_none()

        if not agent:
            await websocket.send_json({"error": "Agent not found or inactive"})
            await websocket.close(code=4004)
            return

        # Snapshot config before leaving the DB session
        agent_cfg = {
            "id": agent.id,
            "system_prompt": agent.system_prompt,
            "welcome_message": agent.welcome_message,
            "pipeline_type": (
                agent.pipeline_type.value
                if hasattr(agent.pipeline_type, "value")
                else agent.pipeline_type
            ),
            "llm_model": agent.llm_model,
            "stt_provider": agent.stt_provider,
            "tts_provider": agent.tts_provider,
            "tts_voice": agent.tts_voice,
            "language": agent.language,
            "max_duration_seconds": agent.max_duration_seconds,
            "participant_id_mode": agent.participant_id_mode,
        }

        # ── 2. Resolve participant_id ──────────────────────────────
        participant_id: str | None = None

        if agent_cfg["participant_id_mode"] == ParticipantIdMode.RANDOM:
            participant_id = secrets.token_urlsafe(8)

        elif agent_cfg["participant_id_mode"] == ParticipantIdMode.PREDEFINED:
            if not pid:
                await websocket.send_json(
                    {"error": "This interview requires a valid participant link."}
                )
                await websocket.close(code=4003)
                return
            pid_result = await db.execute(
                select(ParticipantIdentifier).where(
                    ParticipantIdentifier.agent_id == agent_cfg["id"],
                    ParticipantIdentifier.identifier == pid,
                )
            )
            pid_record = pid_result.scalar_one_or_none()
            if not pid_record:
                await websocket.send_json({"error": "Invalid participant identifier."})
                await websocket.close(code=4003)
                return
            if pid_record.used:
                await websocket.send_json(
                    {"error": "This participant link has already been used."}
                )
                await websocket.close(code=4003)
                return
            participant_id = pid

        elif agent_cfg["participant_id_mode"] == ParticipantIdMode.INPUT:
            participant_id = pid  # May be None if they didn't enter one

        # ── 3. Create a new session ────────────────────────────────
        session = Session(
            id=uuid.uuid4(),
            agent_id=agent_cfg["id"],
            status=SessionStatus.ACTIVE,
            participant_id=participant_id,
        )
        db.add(session)
        await db.commit()
        session_id = session.id
        start_time = datetime.now(timezone.utc)

        # Mark predefined ID as used
        if (
            agent_cfg["participant_id_mode"] == ParticipantIdMode.PREDEFINED
            and pid
        ):
            pid_result2 = await db.execute(
                select(ParticipantIdentifier).where(
                    ParticipantIdentifier.agent_id == agent_cfg["id"],
                    ParticipantIdentifier.identifier == pid,
                )
            )
            pid_record2 = pid_result2.scalar_one_or_none()
            if pid_record2:
                pid_record2.used = True
                pid_record2.session_id = session_id
                await db.commit()

    logger.info(
        f"Interview started: session={session_id}, agent={agent_cfg['id']}, "
        f"widget_key={widget_key}, participant_id={participant_id}"
    )

    # ── 4. Build & run the Pipecat pipeline ────────────────────────
    final_status = SessionStatus.COMPLETED
    try:
        from pipecat.pipeline.runner import PipelineRunner
        from app.pipeline.runner import build_pipeline

        # Notify callback → publishes to Redis for live monitoring
        async def _notify(payload: dict):
            await publish_transcript_event(str(session_id), payload)

        task = await build_pipeline(
            websocket=websocket,
            session_id=session_id,
            system_prompt=agent_cfg["system_prompt"],
            welcome_message=agent_cfg["welcome_message"],
            pipeline_type=agent_cfg["pipeline_type"],
            llm_model=agent_cfg["llm_model"],
            stt_provider=agent_cfg["stt_provider"],
            tts_provider=agent_cfg["tts_provider"],
            tts_voice=agent_cfg["tts_voice"],
            language=agent_cfg["language"],
            max_duration_seconds=agent_cfg["max_duration_seconds"],
            notify_callback=_notify,
        )

        runner = PipelineRunner(handle_sigint=False, handle_sigterm=False)

        # Run with a hard timeout so we never leave zombie pipelines.
        timeout = agent_cfg["max_duration_seconds"] or _MAX_PIPELINE_SECONDS
        # Add generous padding beyond the configured session timeout
        timeout = min(timeout + 60, _MAX_PIPELINE_SECONDS)
        try:
            await asyncio.wait_for(runner.run(task), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(
                f"Interview {session_id}: hard timeout after {timeout}s"
            )
            final_status = SessionStatus.TIMED_OUT

    except WebSocketDisconnect:
        logger.info(f"Interview {session_id}: participant disconnected")
    except asyncio.CancelledError:
        logger.info(f"Interview {session_id}: task cancelled")
    except Exception as exc:
        logger.exception(f"Interview {session_id}: pipeline error — {exc}")
        final_status = SessionStatus.ERROR
    finally:
        # ── 5. Finalise session ────────────────────────────────────
        try:
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()

            async with async_session_factory() as db:
                sess = await db.get(Session, session_id)
                if sess:
                    sess.status = final_status
                    sess.ended_at = end_time
                    sess.duration_seconds = duration
                    await db.commit()

            # Broadcast session_ended event so live monitors close cleanly
            await publish_transcript_event(
                str(session_id),
                {
                    "type": "session_ended",
                    "status": final_status.value,
                    "duration_seconds": round(duration, 1),
                },
            )

            logger.info(
                f"Interview ended: session={session_id}, "
                f"status={final_status.value}, duration={duration:.1f}s"
            )
        except Exception as cleanup_exc:
            logger.error(
                f"Interview {session_id}: failed to finalise session — {cleanup_exc}"
            )
