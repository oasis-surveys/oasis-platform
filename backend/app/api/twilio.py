"""
OASIS — Twilio integration endpoints.

Provides two endpoints for Twilio Media Streams:

1. POST /api/twilio/voice/{agent_id}
   - TwiML webhook that Twilio calls when a phone call comes in.
   - Returns TwiML XML that connects the call to our WebSocket.

2. WS /ws/twilio/{agent_id}
   - WebSocket endpoint that handles Twilio Media Streams protocol.
   - Receives μ-law 8kHz audio from Twilio, converts to PCM16,
     runs through Pipecat pipeline, and sends audio back.

Setup:
  1. Configure your Twilio phone number's Voice webhook to point to:
       https://your-domain.com/api/twilio/voice/{agent_id}
  2. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN in your .env
"""

import asyncio
import json
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect
from loguru import logger
from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.models.agent import Agent, AgentStatus, ParticipantIdMode
from app.models.session import Session, SessionStatus
from app.realtime import publish_transcript_event

router = APIRouter()

# Maximum pipeline runtime (seconds)
_MAX_PIPELINE_SECONDS = 7200


@router.post("/api/twilio/voice/{agent_id}")
async def twilio_voice_webhook(agent_id: str, request: Request):
    """
    TwiML webhook that Twilio calls when a phone call arrives.

    Returns TwiML XML instructing Twilio to connect the call to
    our WebSocket endpoint via Media Streams.
    """
    # Validate the agent exists and is active
    async with async_session_factory() as db:
        result = await db.execute(
            select(Agent).where(
                Agent.id == uuid.UUID(agent_id),
                Agent.status == AgentStatus.ACTIVE.value,
            )
        )
        agent = result.scalar_one_or_none()

    if not agent:
        # Return TwiML that says the agent is unavailable
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say>Sorry, this interview agent is not currently available. Please try again later.</Say>
  <Hangup/>
</Response>"""
        return Response(content=twiml, media_type="application/xml")

    # Build the WebSocket URL for Twilio to connect to
    # Twilio requires wss:// in production; for local dev ws:// works via ngrok
    host = request.headers.get("host", "localhost")
    scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{scheme}://{host}/ws/twilio/{agent_id}"

    logger.info(f"Twilio voice webhook: agent={agent_id}, ws_url={ws_url}")

    # Return TwiML that connects the call to our WebSocket
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{ws_url}">
      <Parameter name="agent_id" value="{agent_id}" />
    </Stream>
  </Connect>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


@router.websocket("/ws/twilio/{agent_id}")
async def twilio_media_stream(websocket: WebSocket, agent_id: str):
    """
    WebSocket endpoint for Twilio Media Streams.

    Twilio connects here after the TwiML <Connect><Stream> instruction.
    The protocol flow:
      1. Twilio sends a "connected" event
      2. Twilio sends a "start" event with streamSid, callSid, etc.
      3. Twilio sends "media" events with base64 μ-law audio
      4. We send "media" events back with base64 μ-law audio
      5. Twilio sends a "stop" event when the call ends
    """
    await websocket.accept()

    # ── 1. Wait for Twilio's initial handshake events ─────────────
    stream_sid = None
    call_sid = None
    custom_params = {}

    try:
        # Read initial messages until we get the "start" event
        while True:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "connected":
                logger.info(f"Twilio connected: protocol={msg.get('protocol')}")
                continue

            if event == "start":
                start_data = msg.get("start", {})
                stream_sid = start_data.get("streamSid")
                call_sid = start_data.get("callSid")
                custom_params = start_data.get("customParameters", {})
                logger.info(
                    f"Twilio stream started: stream_sid={stream_sid}, "
                    f"call_sid={call_sid}, params={custom_params}"
                )
                break

            logger.debug(f"Twilio pre-start event: {event}")

    except asyncio.TimeoutError:
        logger.error("Twilio WebSocket: timed out waiting for start event")
        await websocket.close()
        return
    except WebSocketDisconnect:
        logger.info("Twilio WebSocket: disconnected before start")
        return

    if not stream_sid:
        logger.error("Twilio WebSocket: no stream_sid received")
        await websocket.close()
        return

    # ── 2. Resolve agent ──────────────────────────────────────────
    async with async_session_factory() as db:
        result = await db.execute(
            select(Agent).where(
                Agent.id == uuid.UUID(agent_id),
                Agent.status == AgentStatus.ACTIVE.value,
            )
        )
        agent = result.scalar_one_or_none()

        if not agent:
            logger.error(f"Twilio: agent {agent_id} not found or inactive")
            await websocket.close(code=4004)
            return

        # Snapshot agent config
        agent_cfg = {
            "id": agent.id,
            "study_id": agent.study_id,
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
            "interview_mode": (
                agent.interview_mode.value
                if hasattr(agent.interview_mode, "value")
                else (agent.interview_mode or "free_form")
            ),
            "interview_guide": agent.interview_guide,
        }

        # ── 3. Create session ─────────────────────────────────────
        # For phone calls, use Twilio's callSid as a reference
        participant_id = f"twilio:{call_sid}" if call_sid else secrets.token_urlsafe(8)

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

    logger.info(
        f"Twilio interview started: session={session_id}, agent={agent_cfg['id']}, "
        f"call_sid={call_sid}, stream_sid={stream_sid}"
    )

    # ── 4. Build & run Pipecat pipeline with Twilio serializer ────
    final_status = SessionStatus.COMPLETED
    try:
        from pipecat.pipeline.runner import PipelineRunner
        from app.pipeline.runner import build_twilio_pipeline

        async def _notify(payload: dict):
            await publish_transcript_event(str(session_id), payload)

        task = await build_twilio_pipeline(
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
            interview_mode=agent_cfg.get("interview_mode"),
            interview_guide=agent_cfg.get("interview_guide"),
            stream_sid=stream_sid,
            call_sid=call_sid,
            study_id=agent_cfg["study_id"],
        )

        runner = PipelineRunner(handle_sigint=False, handle_sigterm=False)

        timeout = agent_cfg["max_duration_seconds"] or _MAX_PIPELINE_SECONDS
        timeout = min(timeout + 60, _MAX_PIPELINE_SECONDS)
        try:
            await asyncio.wait_for(runner.run(task), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Twilio interview {session_id}: hard timeout after {timeout}s")
            final_status = SessionStatus.TIMED_OUT

    except WebSocketDisconnect:
        logger.info(f"Twilio interview {session_id}: call disconnected")
    except asyncio.CancelledError:
        logger.info(f"Twilio interview {session_id}: task cancelled")
    except Exception as exc:
        logger.exception(f"Twilio interview {session_id}: pipeline error — {exc}")
        final_status = SessionStatus.ERROR
    finally:
        # ── 5. Finalise session ───────────────────────────────────
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

            await publish_transcript_event(
                str(session_id),
                {
                    "type": "session_ended",
                    "status": final_status.value,
                    "duration_seconds": round(duration, 1),
                },
            )

            logger.info(
                f"Twilio interview ended: session={session_id}, "
                f"status={final_status.value}, duration={duration:.1f}s"
            )
        except Exception as cleanup_exc:
            logger.error(
                f"Twilio interview {session_id}: failed to finalise — {cleanup_exc}"
            )
