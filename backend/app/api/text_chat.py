"""
OASIS — WebSocket endpoint for text-based chat interviews.

When an agent has modality="text", the frontend connects to:
    ws://host/ws/chat/{widget_key}?pid=<optional>

This endpoint:
1. Looks up the agent by widget_key
2. Resolves participant_id
3. Creates a Session
4. Runs a simple LLM chat loop (no Pipecat, no audio)
5. Logs transcript entries for researcher review
"""

import asyncio
import json
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from loguru import logger
from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.models.agent import Agent, AgentStatus, ParticipantIdMode, ParticipantIdentifier
from app.models.session import (
    Session,
    SessionStatus,
    TranscriptEntry,
    SpeakerRole,
    aggregate_session_tokens,
)
from app.realtime import publish_transcript_event
from app.session_manager import register_session, unregister_session

router = APIRouter()

_MAX_CHAT_DURATION = 7200  # 2 hours absolute ceiling


async def _get_key(field: str) -> str:
    """Get effective API key: dashboard override > .env value."""
    try:
        from app.api.settings import get_effective_key
        return await get_effective_key(field)
    except Exception:
        return getattr(settings, field, "")


_REALTIME_TO_CHAT: dict[str, str] = {
    # OpenAI Realtime → chat equivalents
    "openai-realtime/gpt-4o-realtime-preview": "gpt-4o",
    "openai-realtime/gpt-4o-mini-realtime-preview": "gpt-4o-mini",
    "openai-realtime/gpt-realtime-1.5": "gpt-4.1",
    # Gemini Live → chat equivalents
    "google/gemini-2.5-flash-native-audio": "google/gemini-2.5-flash",
    "google/gemini-2.0-flash-live": "google/gemini-2.0-flash",
}


def _resolve_chat_model(model: str) -> str:
    """
    Map voice-to-voice / realtime models to their chat equivalents.

    Text chat agents can only use chat-completion models. If a user
    accidentally configures a realtime model for a text agent, we
    silently remap it so the interview still works.
    """
    # Exact match
    if model in _REALTIME_TO_CHAT:
        return _REALTIME_TO_CHAT[model]

    # Partial match on known realtime keywords
    lower = model.lower()
    if "realtime" in lower or "native-audio" in lower or "live" in lower:
        # Best-effort fallback
        if "gemini" in lower:
            return "google/gemini-2.5-flash"
        if "gpt" in lower:
            return "gpt-4.1"
        return "gpt-4.1"  # safe default

    return model


async def _maybe_inject_rag_context(
    messages: list[dict],
    study_id: uuid.UUID | None,
    user_text: str,
) -> list[dict]:
    """
    If the study has a knowledge base, search it for context relevant to
    the user's latest message and inject it as a system message so the LLM
    can ground its answer in the uploaded documents.

    Returns a (possibly augmented) copy of the messages list.
    """
    if not study_id or not user_text.strip():
        return messages

    try:
        from app.knowledge.embeddings import search_similar_chunks

        async with async_session_factory() as db:
            results = await search_similar_chunks(
                db=db,
                study_id=study_id,
                query=user_text,
                top_k=5,
            )

        if not results:
            return messages

        # Build context block
        context_parts = []
        for i, r in enumerate(results, 1):
            context_parts.append(
                f"[Source: {r['title']}] (relevance: {r['similarity']})\n"
                f"{r['content']}"
            )
        context_text = "\n\n---\n\n".join(context_parts)
        rag_message = {
            "role": "system",
            "content": (
                "The following information from the study's knowledge base may "
                "be relevant to the participant's question. Use it to inform "
                "your response if appropriate, but do not mention that you are "
                "consulting a knowledge base.\n\n"
                f"{context_text}"
            ),
        }

        # Insert RAG context just before the latest user message
        augmented = messages[:-1] + [rag_message, messages[-1]]
        logger.debug(
            f"RAG injected {len(results)} chunks for text-chat "
            f"(study={study_id})"
        )
        return augmented

    except Exception as exc:
        logger.warning(f"Text-chat RAG lookup failed (non-fatal): {exc}")
        return messages


async def _call_llm(
    messages: list[dict],
    model: str,
    study_id: uuid.UUID | None = None,
) -> dict:
    """
    Call the LLM via LiteLLM and return the assistant message + token usage.

    If the study has a knowledge base, relevant context is injected into
    the messages before calling the LLM (inline RAG — unlike voice pipelines
    that use Pipecat's function-calling tool approach).
    """
    import litellm

    # Remap realtime/v2v models to their chat equivalents
    original_model = model
    model = _resolve_chat_model(model)
    if model != original_model:
        logger.info(f"Text chat: remapped v2v model '{original_model}' → '{model}'")

    # ── RAG context injection ──────────────────────────────────────
    # Extract latest user message for the similarity search
    last_user_text = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_text = m.get("content", "")
            break
    messages = await _maybe_inject_rag_context(messages, study_id, last_user_text)

    # Resolve model to litellm format
    litellm_model = model
    if model.startswith("scaleway/"):
        litellm_model = f"openai/{model.split('/', 1)[1]}"

    # Set up API keys
    api_key = await _get_key("openai_api_key")
    kwargs: dict = {
        "model": litellm_model,
        "messages": messages,
        "max_tokens": 2048,
        "temperature": 0.7,
    }

    if model.startswith("scaleway/"):
        scw_key = await _get_key("scaleway_secret_key")
        kwargs["api_key"] = scw_key
        kwargs["api_base"] = "https://api.scaleway.ai/v1"
    elif model.startswith("azure/"):
        kwargs["api_key"] = await _get_key("azure_openai_api_key")
        kwargs["api_base"] = getattr(settings, "azure_openai_endpoint", "")
        kwargs["api_version"] = getattr(settings, "azure_openai_api_version", "2024-02-01")
    elif model.startswith("gcp/"):
        gcp_model = model.split("/", 1)[1]
        litellm_model = f"vertex_ai/{gcp_model}"
        kwargs["model"] = litellm_model
        kwargs["api_key"] = await _get_key("gcp_api_key")
    elif model.startswith("google/"):
        google_model = model.split("/", 1)[1]
        litellm_model = f"gemini/{google_model}"
        kwargs["model"] = litellm_model
        kwargs["api_key"] = await _get_key("google_api_key")
    else:
        kwargs["api_key"] = api_key

    response = await litellm.acompletion(**kwargs)

    content = response.choices[0].message.content or ""
    usage = response.usage
    return {
        "content": content,
        "prompt_tokens": usage.prompt_tokens if usage else None,
        "completion_tokens": usage.completion_tokens if usage else None,
    }


async def _log_turn(
    session_id: uuid.UUID,
    role: SpeakerRole,
    content: str,
    sequence: int,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
):
    """Log a transcript entry to the database."""
    async with async_session_factory() as db:
        entry = TranscriptEntry(
            id=uuid.uuid4(),
            session_id=session_id,
            role=role,
            content=content,
            sequence=sequence,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            spoken_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        await db.commit()


@router.websocket("/ws/chat/{widget_key}")
async def text_chat_ws(
    websocket: WebSocket,
    widget_key: str,
    pid: str | None = Query(None),
):
    """
    Text-based chat interview WebSocket endpoint.

    Protocol (JSON over WebSocket):
      Client → Server: { "type": "message", "text": "..." }
      Server → Client: { "type": "message", "text": "...", "role": "agent" }
      Server → Client: { "type": "welcome", "text": "...", "avatar": "..." }
      Server → Client: { "type": "ended" }
      Server → Client: { "type": "error", "text": "..." }
    """
    await websocket.accept()

    # ── 1. Resolve agent ──────────────────────────────────────────
    async with async_session_factory() as db:
        result = await db.execute(
            select(Agent).where(
                Agent.widget_key == widget_key,
                Agent.status == AgentStatus.ACTIVE.value,
            )
        )
        agent = result.scalar_one_or_none()

        if not agent:
            await websocket.send_json({"type": "error", "text": "Agent not found or inactive"})
            await websocket.close(code=4004, reason="Agent not found or inactive")
            return

        # Snapshot config
        agent_cfg = {
            "id": agent.id,
            "study_id": agent.study_id,
            "system_prompt": agent.system_prompt,
            "welcome_message": agent.welcome_message,
            "llm_model": agent.llm_model,
            "language": agent.language,
            "max_duration_seconds": agent.max_duration_seconds,
            "participant_id_mode": agent.participant_id_mode,
            "avatar": agent.avatar or "neutral",
            "interview_mode": (
                agent.interview_mode.value
                if hasattr(agent.interview_mode, "value")
                else (agent.interview_mode or "free_form")
            ),
            "interview_guide": agent.interview_guide,
        }

        # ── 2. Resolve participant_id ─────────────────────────────
        participant_id: str | None = None

        if agent_cfg["participant_id_mode"] == ParticipantIdMode.RANDOM:
            participant_id = secrets.token_urlsafe(8)
        elif agent_cfg["participant_id_mode"] == ParticipantIdMode.PREDEFINED:
            if not pid:
                await websocket.send_json({"type": "error", "text": "This interview requires a valid participant link."})
                await websocket.close(code=4003, reason="Missing participant ID")
                return
            pid_result = await db.execute(
                select(ParticipantIdentifier).where(
                    ParticipantIdentifier.agent_id == agent_cfg["id"],
                    ParticipantIdentifier.identifier == pid,
                )
            )
            pid_record = pid_result.scalar_one_or_none()
            if not pid_record:
                await websocket.send_json({"type": "error", "text": "Invalid participant identifier."})
                await websocket.close(code=4003, reason="Invalid participant ID")
                return
            if pid_record.used:
                await websocket.send_json({"type": "error", "text": "This participant link has already been used."})
                await websocket.close(code=4003, reason="Participant ID already used")
                return
            participant_id = pid
        elif agent_cfg["participant_id_mode"] == ParticipantIdMode.INPUT:
            # Reject empty/blank IDs — INPUT mode requires the participant
            # to actually type something, otherwise sessions become anonymous.
            if not pid or not pid.strip():
                await websocket.send_json(
                    {"error": "Please provide a participant ID before starting the chat."}
                )
                await websocket.close(code=4003, reason="Missing participant ID")
                return
            participant_id = pid.strip()

        # ── 3. Create session ─────────────────────────────────────
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
        if agent_cfg["participant_id_mode"] == ParticipantIdMode.PREDEFINED and pid:
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
        f"Text chat started: session={session_id}, agent={agent_cfg['id']}, "
        f"widget_key={widget_key}, participant_id={participant_id}"
    )

    await register_session(
        session_id=session_id,
        agent_id=agent_cfg["id"],
        max_duration_seconds=agent_cfg["max_duration_seconds"],
    )

    # ── 4. Build system prompt ────────────────────────────────────
    system_prompt = agent_cfg["system_prompt"]
    if (
        agent_cfg["interview_mode"] == "structured"
        and agent_cfg["interview_guide"]
    ):
        from app.pipeline.interview_guide import build_structured_prompt
        system_prompt = build_structured_prompt(system_prompt, agent_cfg["interview_guide"])

    # Add text-chat specific instructions
    system_prompt += (
        "\n\n---\n"
        "You are communicating via text chat (not voice). Keep responses "
        "conversational but concise. Use natural written language."
    )

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    sequence = 0

    # ── 5. Send welcome message ───────────────────────────────────
    welcome = agent_cfg["welcome_message"]
    if welcome:
        messages.append({"role": "assistant", "content": welcome})
        await websocket.send_json({
            "type": "welcome",
            "text": welcome,
            "avatar": agent_cfg["avatar"],
        })
        sequence += 1
        await _log_turn(session_id, SpeakerRole.AGENT, welcome, sequence)
        await publish_transcript_event(str(session_id), {
            "type": "transcript",
            "role": "agent",
            "content": welcome,
            "sequence": sequence,
        })

    # ── 6. Chat loop ──────────────────────────────────────────────
    final_status = SessionStatus.COMPLETED
    try:
        timeout = agent_cfg["max_duration_seconds"] or _MAX_CHAT_DURATION

        while True:
            # Check duration
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            if elapsed > timeout:
                await websocket.send_json({
                    "type": "ended",
                    "text": "Interview time limit reached. Thank you for your participation.",
                })
                final_status = SessionStatus.TIMED_OUT
                break

            # Wait for user message
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=max(timeout - elapsed, 1),
                )
            except asyncio.TimeoutError:
                await websocket.send_json({
                    "type": "ended",
                    "text": "Interview time limit reached. Thank you for your participation.",
                })
                final_status = SessionStatus.TIMED_OUT
                break

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") != "message" or not msg.get("text", "").strip():
                continue

            user_text = msg["text"].strip()

            # Log user turn
            sequence += 1
            await _log_turn(session_id, SpeakerRole.USER, user_text, sequence)
            await publish_transcript_event(str(session_id), {
                "type": "transcript",
                "role": "user",
                "content": user_text,
                "sequence": sequence,
            })

            messages.append({"role": "user", "content": user_text})

            # Call LLM
            try:
                # Send typing indicator
                await websocket.send_json({"type": "typing"})

                llm_result = await _call_llm(
                    messages=messages,
                    model=agent_cfg["llm_model"],
                    study_id=agent_cfg["study_id"],
                )
                agent_text = llm_result["content"]
                messages.append({"role": "assistant", "content": agent_text})

                # Log agent turn
                sequence += 1
                await _log_turn(
                    session_id,
                    SpeakerRole.AGENT,
                    agent_text,
                    sequence,
                    prompt_tokens=llm_result["prompt_tokens"],
                    completion_tokens=llm_result["completion_tokens"],
                )
                await publish_transcript_event(str(session_id), {
                    "type": "transcript",
                    "role": "agent",
                    "content": agent_text,
                    "sequence": sequence,
                })

                await websocket.send_json({
                    "type": "message",
                    "text": agent_text,
                    "role": "agent",
                })

            except Exception as llm_err:
                logger.exception(f"Chat {session_id}: LLM error — {llm_err}")
                await websocket.send_json({
                    "type": "error",
                    "text": "Sorry, I encountered an issue. Please try again.",
                })

    except WebSocketDisconnect:
        logger.info(f"Chat {session_id}: participant disconnected")
    except asyncio.CancelledError:
        logger.info(f"Chat {session_id}: task cancelled")
    except Exception as exc:
        logger.exception(f"Chat {session_id}: error — {exc}")
        final_status = SessionStatus.ERROR
    finally:
        # ── 7. Finalise session ───────────────────────────────────
        try:
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()

            async with async_session_factory() as db:
                sess = await db.get(Session, session_id)
                if sess:
                    sess.status = final_status
                    sess.ended_at = end_time
                    sess.duration_seconds = duration
                    sess.total_tokens = await aggregate_session_tokens(db, session_id)
                    await db.commit()

            await publish_transcript_event(str(session_id), {
                "type": "session_ended",
                "status": final_status.value,
                "duration_seconds": round(duration, 1),
            })

            logger.info(
                f"Chat ended: session={session_id}, "
                f"status={final_status.value}, duration={duration:.1f}s"
            )
            await unregister_session(session_id)

        except Exception as cleanup_exc:
            logger.error(f"Chat {session_id}: failed to finalise — {cleanup_exc}")
