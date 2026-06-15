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
import time
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
_KEEPALIVE_INTERVAL = 20  # seconds between keepalive pings

# OpenAI EU regional API (mirrors app.pipeline.runner)
_OPENAI_EU_BASE_URL = "https://eu.api.openai.com/v1"


async def _get_key(field: str) -> str:
    """Get effective API key: dashboard override > .env value."""
    try:
        from app.api.settings import get_effective_key
        return await get_effective_key(field)
    except Exception:
        return getattr(settings, field, "")


async def _openai_use_eu() -> bool:
    """Whether OpenAI HTTP calls should use the EU regional endpoint."""
    try:
        from app.api.settings import get_effective_flag

        return await get_effective_flag("openai_use_eu")
    except Exception:
        return bool(getattr(settings, "openai_use_eu", False))


async def _openai_api_base() -> str | None:
    """LiteLLM api_base for OpenAI chat models, or None for the default region."""
    return _OPENAI_EU_BASE_URL if await _openai_use_eu() else None


_REALTIME_TO_CHAT: dict[str, str] = {
    # OpenAI Realtime → chat equivalents
    "openai-realtime/gpt-4o-realtime-preview": "gpt-4o",
    "openai-realtime/gpt-4o-mini-realtime-preview": "gpt-4o-mini",
    "openai-realtime/gpt-realtime-1.5": "gpt-4.1",
    "openai-realtime/gpt-realtime-2": "gpt-4.1",
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
        # User-role note: mid-conversation system messages are rejected by
        # some chat APIs (OpenAI gpt-5.x) with a 400 error.
        rag_message = {
            "role": "user",
            "content": (
                "[Knowledge base context — this is background material for "
                "you, not something the participant said. Use it to inform "
                "your response if appropriate, but do not mention that you "
                "are consulting a knowledge base.]\n\n"
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
    elif model.startswith("custom/"):
        custom_model = model.split("/", 1)[1]
        base_url = await _get_key("openai_compatible_llm_url") or settings.openai_compatible_llm_url
        if not base_url:
            raise ValueError(
                "OPENAI_COMPATIBLE_LLM_URL is not set. Provide a base URL "
                "(e.g. http://my-litellm:4000/v1) for your custom OpenAI-"
                "compatible endpoint, or pick a built-in provider."
            )
        kwargs["model"] = f"openai/{custom_model}"
        kwargs["api_base"] = base_url
        kwargs["api_key"] = await _get_key("openai_compatible_llm_api_key") or "not-needed"
    elif model.startswith("anthropic/"):
        anthropic_key = await _get_key("anthropic_api_key")
        if not anthropic_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env file or dashboard."
            )
        kwargs["api_key"] = anthropic_key
        kwargs["model"] = model
    else:
        # OpenAI chat models (openai/ prefix, bare gpt-* ids, etc.)
        kwargs["api_key"] = api_key
        eu_base = await _openai_api_base()
        if eu_base:
            kwargs["api_base"] = eu_base

    response = await litellm.acompletion(**kwargs)

    content = response.choices[0].message.content or ""
    usage = response.usage
    return {
        "content": content,
        "prompt_tokens": usage.prompt_tokens if usage else None,
        "completion_tokens": usage.completion_tokens if usage else None,
    }


async def _keepalive_loop(ws: WebSocket, stop: asyncio.Event) -> None:
    """Send periodic pings to prevent idle-timeout disconnections (e.g. iOS Safari)."""
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=_KEEPALIVE_INTERVAL)
        except asyncio.TimeoutError:
            try:
                await ws.send_json({"type": "ping"})
            except Exception:
                break


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


async def _record_engagement_turn(
    session_id: uuid.UUID,
    scorer,
    detector,
    *,
    sequence: int,
    text: str,
    language: str | None,
    response_latency_ms: int | None,
) -> None:
    """
    Compute and persist engagement metrics for one text-chat user turn.

    Text interviews expose only lexical and timing signals (no audio), so
    voiced duration, speech rate, and energy stay null. Never raises — a
    failure here must not break the interview.
    """
    from app.engagement.features import TurnFeatures
    from app.models.engagement import EngagementEvent, EngagementTurn

    try:
        features = TurnFeatures.from_turn(
            transcript_sequence=sequence,
            text=text or "",
            language=language,
            response_latency_ms=response_latency_ms,
            voiced_ms=None,
            modality="text",
        )
        result = scorer.score(features)
        events = detector.observe(result.label)
        event_types = [e.event_type for e in events]

        async with async_session_factory() as db:
            db.add(
                EngagementTurn(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    transcript_sequence=sequence,
                    response_latency_ms=features.response_latency_ms,
                    voiced_ms=None,
                    word_count=features.word_count,
                    char_count=features.char_count,
                    speech_rate_wpm=None,
                    filler_count=features.filler_count,
                    rms_energy=None,
                    score=result.score,
                    label=result.label,
                    extras={
                        "flags": result.flags,
                        "components": result.components,
                        "modality": "text",
                    },
                )
            )
            for ev in events:
                db.add(
                    EngagementEvent(
                        id=uuid.uuid4(),
                        session_id=session_id,
                        transcript_sequence=sequence,
                        event_type=ev.event_type,
                        score_at_event=result.score,
                        payload=ev.payload,
                    )
                )
            await db.commit()
        return {"triggers": set(event_types) | set(result.flags)}
    except Exception as exc:
        logger.error(f"Text engagement: failed to record turn {sequence}: {exc}")
        return None


async def _apply_text_adaptation(
    session_id: uuid.UUID,
    engine,
    *,
    sequence: int,
    triggers: set[str],
    messages: list[dict],
) -> None:
    """
    Evaluate the adaptive policy for a text turn and, in live mode, inject a
    system instruction before the next LLM call. Speed actions do not apply to
    text. Every action is recorded for disclosure. Never raises.
    """
    import time

    from app.engagement.adaptive import PROMPT, guidance_message
    from app.models.engagement import AdaptiveAction

    try:
        actions = engine.evaluate(triggers, time.monotonic())
        if not actions:
            return
        live = engine.policy.is_live
        async with async_session_factory() as db:
            for act in actions:
                applied = False
                if act.type == PROMPT and act.instruction:
                    if live:
                        # User-role note: mid-conversation system messages are
                        # rejected by some chat APIs (OpenAI gpt-5.x, 400).
                        messages.append(guidance_message(act.instruction))
                        applied = True
                    detail = {"applied": applied, "instruction": act.instruction}
                else:
                    # tts_speed has no effect in text chat.
                    detail = {
                        "applied": False,
                        "params": act.params,
                        "note": "speed_not_applicable_to_text",
                    }
                db.add(
                    AdaptiveAction(
                        id=uuid.uuid4(),
                        session_id=session_id,
                        transcript_sequence=sequence,
                        trigger=act.trigger,
                        action=act.action,
                        mode=engine.policy.mode,
                        detail=detail,
                    )
                )
            await db.commit()
    except Exception as exc:
        logger.error(f"Text adaptation: failed at turn {sequence}: {exc}")


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
            "track_engagement": bool(agent.track_engagement),
            "engagement_config": agent.engagement_config,
            "adaptive_enabled": bool(agent.adaptive_enabled),
            "adaptive_policy": agent.adaptive_policy,
            "widget_show_progress": bool(agent.widget_show_progress),
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
                await websocket.send_json({
                    "type": "error",
                    "text": "Please provide a participant ID before starting the chat.",
                })
                await websocket.close(code=4003, reason="Missing participant ID")
                return
            participant_id = pid.strip()

        # Adaptation can affect this chat only when engagement is on, the
        # policy has rules, and the mode is live.
        _policy = agent_cfg.get("adaptive_policy") or {}
        adaptive_active = bool(
            agent_cfg["track_engagement"]
            and agent_cfg["adaptive_enabled"]
            and _policy.get("rules")
            and _policy.get("mode") == "live"
        )

        # ── 3. Create session ─────────────────────────────────────
        session = Session(
            id=uuid.uuid4(),
            agent_id=agent_cfg["id"],
            status=SessionStatus.ACTIVE,
            participant_id=participant_id,
            adaptive_active=adaptive_active,
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
    is_structured = bool(
        agent_cfg["interview_mode"] == "structured"
        and agent_cfg["interview_guide"]
    )
    # Progress bar: only meaningful for structured chats with the toggle on.
    show_progress = bool(is_structured and agent_cfg["widget_show_progress"])
    progress_total = (
        len(agent_cfg["interview_guide"].get("questions", []))
        if is_structured
        else 0
    )
    reported_progress = 0
    if is_structured:
        from app.pipeline.interview_guide import build_structured_prompt
        system_prompt = build_structured_prompt(
            system_prompt,
            agent_cfg["interview_guide"],
            emit_progress=show_progress,
        )

    # Add text-chat specific instructions
    system_prompt += (
        "\n\n---\n"
        "You are communicating via text chat (not voice). Keep responses "
        "conversational but concise. Use natural written language."
    )

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    sequence = 0

    # ── Engagement metrics (text profile; observational, lexical + timing) ──
    engagement_scorer = None
    engagement_detector = None
    adaptive_engine = None
    agent_sent_at: float | None = None
    if agent_cfg["track_engagement"]:
        from app.engagement.events import EventDetector
        from app.engagement.scorer import RuleBasedScorer, ScorerConfig

        _eng_cfg = ScorerConfig.from_dict(
            agent_cfg["engagement_config"], modality="text"
        )
        engagement_scorer = RuleBasedScorer(_eng_cfg)
        engagement_detector = EventDetector(_eng_cfg)
        logger.info(f"Engagement tracking enabled for text session {session_id}")

        if agent_cfg["adaptive_enabled"]:
            from app.engagement.adaptive import AdaptivePolicy, AdaptivePolicyEngine

            _policy_obj = AdaptivePolicy.from_dict(agent_cfg["adaptive_policy"])
            if _policy_obj.rules:
                adaptive_engine = AdaptivePolicyEngine(_policy_obj)
                logger.info(
                    f"Adaptive behavior ({_policy_obj.mode}) enabled for text "
                    f"session {session_id}"
                )

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
        if engagement_scorer:
            agent_sent_at = time.monotonic()

    # ── 6. Chat loop ──────────────────────────────────────────────
    keepalive_stop = asyncio.Event()
    keepalive_task = asyncio.create_task(_keepalive_loop(websocket, keepalive_stop))
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

            if engagement_scorer:
                latency_ms = (
                    int((time.monotonic() - agent_sent_at) * 1000)
                    if agent_sent_at is not None
                    else None
                )
                eng = await _record_engagement_turn(
                    session_id,
                    engagement_scorer,
                    engagement_detector,
                    sequence=sequence,
                    text=user_text,
                    language=agent_cfg["language"],
                    response_latency_ms=latency_ms,
                )
                if adaptive_engine and eng and eng.get("triggers"):
                    await _apply_text_adaptation(
                        session_id,
                        adaptive_engine,
                        sequence=sequence,
                        triggers=eng["triggers"],
                        messages=messages,
                    )

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

                # Keep the raw reply (tag included) in the model's own context
                # so it keeps tagging later main questions. The tag is removed
                # from everything the participant and the transcript see below.
                messages.append({"role": "assistant", "content": agent_text})

                display_text = agent_text
                if show_progress:
                    from app.pipeline.interview_guide import strip_progress_marker

                    display_text, marker = strip_progress_marker(agent_text)
                    display_text = display_text.lstrip()
                    if marker is not None:
                        marker = min(marker, progress_total) if progress_total else marker
                        if marker > reported_progress:
                            reported_progress = marker
                            await websocket.send_json({
                                "type": "progress",
                                "current": reported_progress,
                                "total": progress_total,
                            })

                # Log agent turn
                sequence += 1
                await _log_turn(
                    session_id,
                    SpeakerRole.AGENT,
                    display_text,
                    sequence,
                    prompt_tokens=llm_result["prompt_tokens"],
                    completion_tokens=llm_result["completion_tokens"],
                )
                await publish_transcript_event(str(session_id), {
                    "type": "transcript",
                    "role": "agent",
                    "content": display_text,
                    "sequence": sequence,
                })

                await websocket.send_json({
                    "type": "message",
                    "text": display_text,
                    "role": "agent",
                })
                if engagement_scorer:
                    agent_sent_at = time.monotonic()

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
        keepalive_stop.set()
        keepalive_task.cancel()
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
