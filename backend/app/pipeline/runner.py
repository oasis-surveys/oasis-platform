"""
OASIS — Pipecat pipeline builder (pipecat 1.x).

Supports two pipeline types:

  Modular:
    Transport(in) → STT → UserCapture → UserCtx → LLM → TranscriptLogger → TTS → Transport(out)

  Voice-to-Voice:
    OpenAI Realtime:   Transport(in) → RealtimeLLM → UserCapture → TranscriptLogger → Transport(out)
    Gemini Live:       Transport(in) → GeminiLiveLLM → UserCapture → TranscriptLogger → Transport(out)

Pipecat 1.x notes:
  - VAD and turn detection live on LLMUserAggregatorParams, not the transport.
  - Silence handling uses the aggregator's on_user_turn_idle event, not the
    removed UserIdleProcessor.
"""

import uuid
from typing import Optional

from loguru import logger

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.frames.frames import (
    EndFrame,
    LLMContextFrame,
    TTSSpeakFrame,
)

from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)

from app.config import settings
from app.providers.catalog import resolve_llm_api_kind
from app.database import async_session_factory
from app.pipeline.transcript_logger import (
    TranscriptLoggerState,
    TranscriptUserCapture,
    TranscriptLogger,
)
from app.audio.recording import (
    AgentAudioTap,
    AudioRecordingManager,
    UserAudioTap,
)
from app.audio.storage import build_session_prefix, get_audio_storage


# ── OpenAI EU data-residency endpoints ─────────────────────────────────────
# When the openai_use_eu flag is on, we route every OpenAI HTTP/WebSocket call
# through the EU regional API. See https://developers.openai.com/api/docs/guides/your-data
_OPENAI_EU_BASE_URL = "https://eu.api.openai.com/v1"
_OPENAI_EU_REALTIME_URL = "wss://eu.api.openai.com/v1/realtime"
_OPENAI_DEFAULT_REALTIME_URL = "wss://api.openai.com/v1/realtime"


async def _openai_use_eu() -> bool:
    """Whether the OpenAI EU data-residency flag is currently enabled."""
    try:
        from app.api.settings import get_effective_flag
        return await get_effective_flag("openai_use_eu")
    except Exception:
        return bool(getattr(settings, "openai_use_eu", False))


async def _openai_base_url() -> Optional[str]:
    """Return the EU base URL for OpenAI HTTP endpoints when the flag is on."""
    return _OPENAI_EU_BASE_URL if await _openai_use_eu() else None


async def _openai_realtime_base_url() -> str:
    """Return the WebSocket URL for the OpenAI Realtime API."""
    return (
        _OPENAI_EU_REALTIME_URL
        if await _openai_use_eu()
        else _OPENAI_DEFAULT_REALTIME_URL
    )


async def _setup_audio_recording(
    *,
    record_audio: bool,
    session_id: uuid.UUID,
    study_id: uuid.UUID,
    agent_id: uuid.UUID,
    participant_id: Optional[str],
    pipeline_type: str,
) -> tuple[Optional[AudioRecordingManager], UserAudioTap, AgentAudioTap]:
    """Create session audio recorder when storage is configured and agent opts in."""
    storage = await get_audio_storage()
    if not record_audio or not storage:
        return None, UserAudioTap(None), AgentAudioTap(None)

    prefix = build_session_prefix(
        study_id=study_id,
        agent_id=agent_id,
        participant_id=participant_id,
        session_id=session_id,
    )
    manager = AudioRecordingManager(
        storage,
        session_prefix=prefix,
        session_id=session_id,
        pipeline_type=pipeline_type,
    )
    logger.info(f"Audio recording enabled for session {session_id} at {prefix}")
    return manager, UserAudioTap(manager), AgentAudioTap(manager)


async def _get_key(field: str) -> str:
    """
    Get effective API key: dashboard override (Redis) > .env value.

    This allows researchers to set API keys via the dashboard without
    needing to restart the backend.
    """
    try:
        from app.api.settings import get_effective_key
        return await get_effective_key(field)
    except Exception:
        return getattr(settings, field, "")


def _v2v_system_prompt_with_welcome(
    system_prompt: str, welcome_message: Optional[str]
) -> str:
    """
    Bake the welcome message into the system prompt for V2V pipelines.

    V2V backends (OpenAI Realtime, Gemini Live) drive their own conversation
    state and expect the bot's first turn to come out of the model itself,
    not as a pre-recorded TTS clip. Injecting the welcome as a ``user`` turn
    in the initial context (the previous behaviour) makes the model think the
    *participant* said the welcome line, which produced the "all over the
    place" greetings users were seeing.

    Instead we append a short directive to the system prompt telling the
    model to open with the welcome verbatim and then wait for a response.
    """
    if not welcome_message:
        return system_prompt
    return (
        system_prompt.rstrip()
        + "\n\n---\n"
        + "Begin the conversation by speaking the following greeting "
        + "exactly as written, word for word, before doing anything else. "
        + "After speaking it, stop and wait for the participant to "
        + "respond before continuing.\n\n"
        + f'Greeting: "{welcome_message}"'
    )


async def build_twilio_pipeline(
    *,
    websocket,
    session_id: uuid.UUID,
    system_prompt: str,
    welcome_message: Optional[str],
    pipeline_type: str = "modular",
    llm_model: str,
    stt_provider: str = "deepgram",
    stt_model: Optional[str] = None,
    tts_provider: str = "elevenlabs",
    tts_model: Optional[str] = None,
    tts_voice: Optional[str] = None,
    language: str = "en",
    max_duration_seconds: Optional[int] = None,
    notify_callback=None,
    stream_sid: str = "",
    call_sid: Optional[str] = None,
    study_id: Optional[uuid.UUID] = None,
    interview_mode: Optional[str] = None,
    interview_guide: Optional[dict] = None,
    turn_detection: Optional[str] = None,
) -> PipelineTask:
    """
    Build a Pipecat pipeline for Twilio telephony.

    Uses TwilioFrameSerializer to handle μ-law ↔ PCM16 conversion
    and Twilio Media Streams JSON protocol.
    """
    # ── Structured interview prompt enhancement ───────────────────
    effective_prompt = system_prompt
    if interview_mode == "structured" and interview_guide:
        from app.pipeline.interview_guide import build_structured_prompt
        effective_prompt = build_structured_prompt(system_prompt, interview_guide)
        logger.info(
            f"Twilio structured interview: {len(interview_guide.get('questions', []))} questions"
        )

    from pipecat.serializers.twilio import TwilioFrameSerializer

    serializer = TwilioFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        account_sid=settings.twilio_account_sid or None,
        auth_token=settings.twilio_auth_token or None,
        params=TwilioFrameSerializer.InputParams(
            # Disable auto hang-up if no credentials provided
            auto_hang_up=bool(
                settings.twilio_account_sid
                and settings.twilio_auth_token
                and call_sid
            ),
        ),
    )

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
            session_timeout=max_duration_seconds,
        ),
    )

    transcript_state = TranscriptLoggerState(
        session_id=session_id,
        db_session_factory=async_session_factory,
        notify_callback=notify_callback,
    )
    user_capture = TranscriptUserCapture(transcript_state)
    transcript_logger = TranscriptLogger(transcript_state)

    # Twilio calls always use the modular pipeline (STT → LLM → TTS)
    # because the telephony audio is 8kHz μ-law, not suitable for
    # direct V2V endpoints which expect higher-quality audio.
    # However, if the agent is configured for V2V, we still support it.
    if pipeline_type == "voice_to_voice":
        task = await _build_v2v_pipeline(
            transport=transport,
            user_capture=user_capture,
            transcript_logger=transcript_logger,
            llm_model=llm_model,
            system_prompt=effective_prompt,
            welcome_message=welcome_message,
            language=language,
            max_duration_seconds=max_duration_seconds,
            voice=tts_voice,
            study_id=study_id,
        )
    else:
        task = await _build_modular_pipeline(
            transport=transport,
            user_capture=user_capture,
            transcript_logger=transcript_logger,
            llm_model=llm_model,
            system_prompt=effective_prompt,
            welcome_message=welcome_message,
            stt_provider=stt_provider,
            stt_model=stt_model,
            tts_provider=tts_provider,
            tts_model=tts_model,
            tts_voice=tts_voice,
            language=language,
            max_duration_seconds=max_duration_seconds,
            study_id=study_id,
            interview_mode=interview_mode,
            interview_guide=interview_guide,
            turn_detection=turn_detection,
        )

    return task


async def build_pipeline(
    *,
    websocket,
    session_id: uuid.UUID,
    system_prompt: str,
    welcome_message: Optional[str],
    pipeline_type: str = "modular",
    llm_model: str,
    stt_provider: str = "deepgram",
    stt_model: Optional[str] = None,
    tts_provider: str = "elevenlabs",
    tts_model: Optional[str] = None,
    tts_voice: Optional[str] = None,
    language: str = "en",
    max_duration_seconds: Optional[int] = None,
    notify_callback=None,
    study_id: Optional[uuid.UUID] = None,
    agent_id: Optional[uuid.UUID] = None,
    participant_id: Optional[str] = None,
    record_audio: bool = False,
    silence_timeout_seconds: Optional[int] = None,
    silence_prompt: Optional[str] = None,
    interview_mode: Optional[str] = None,
    interview_guide: Optional[dict] = None,
    track_engagement: bool = False,
    engagement_config: Optional[dict] = None,
    adaptive_enabled: bool = False,
    adaptive_policy: Optional[dict] = None,
    widget_show_progress: bool = False,
    turn_detection: Optional[str] = None,
) -> tuple[PipelineTask, Optional[AudioRecordingManager]]:
    """
    Build and return a ready-to-run PipelineTask plus optional audio manager.
    The caller runs `await runner.run(task)` then finalises session audio in DB.
    """

    # ── Structured interview prompt enhancement ───────────────────
    # The progress bar only works on the modular pipeline (the V2V audio stream
    # has no text filter to strip the hidden marker), so we only ask the model
    # to emit markers there.
    emit_progress = bool(
        widget_show_progress
        and interview_mode == "structured"
        and interview_guide
        and pipeline_type != "voice_to_voice"
    )
    effective_prompt = system_prompt
    if interview_mode == "structured" and interview_guide:
        from app.pipeline.interview_guide import build_structured_prompt
        effective_prompt = build_structured_prompt(
            system_prompt, interview_guide, emit_progress=emit_progress
        )
        logger.info(
            f"Structured interview mode: {len(interview_guide.get('questions', []))} questions loaded"
        )

    # ── Progress bar updates (structured modular voice only) ──────
    # Sent to the participant as a JSON text frame on the same WebSocket. The
    # browser already distinguishes binary audio frames from JSON control
    # messages, and these fire only a handful of times per interview.
    _progress_callback = None
    if emit_progress:
        async def _send_progress(current: int, total: int):
            try:
                await websocket.send_json(
                    {"type": "progress", "current": current, "total": total}
                )
            except Exception as exc:
                logger.debug(f"Progress send failed (non-fatal): {exc}")

        _progress_callback = _send_progress

    # ── Transport (WebSocket ↔ browser) ───────────────────────────
    serializer = _build_serializer()

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
            session_timeout=max_duration_seconds,
        ),
    )

    audio_manager, user_tap, agent_tap = await _setup_audio_recording(
        record_audio=record_audio,
        session_id=session_id,
        study_id=study_id or uuid.UUID(int=0),
        agent_id=agent_id or uuid.UUID(int=0),
        participant_id=participant_id,
        pipeline_type=pipeline_type,
    )

    # ── Transcript logging (shared state, two processors) ──────────
    transcript_state = TranscriptLoggerState(
        session_id=session_id,
        db_session_factory=async_session_factory,
        notify_callback=notify_callback,
        audio_manager=audio_manager,
    )
    user_capture = TranscriptUserCapture(transcript_state)
    transcript_logger = TranscriptLogger(transcript_state)

    # ── Engagement metrics (modular voice only, observe-only) ──
    engagement_processor = None
    adaptive_processor = None
    if track_engagement and pipeline_type != "voice_to_voice":
        from app.pipeline.engagement_processor import EngagementProcessor

        # Adaptive behavior consumes per-turn engagement signals.
        adaptive_signals = None
        if adaptive_enabled:
            from app.engagement.adaptive import AdaptivePolicy, AdaptiveSignals
            from app.pipeline.adaptive_processor import AdaptiveBehaviorProcessor

            policy = AdaptivePolicy.from_dict(adaptive_policy)
            if policy.rules:
                adaptive_signals = AdaptiveSignals()
                adaptive_processor = AdaptiveBehaviorProcessor(
                    session_id=session_id,
                    db_session_factory=async_session_factory,
                    signals=adaptive_signals,
                    policy=policy,
                    tts_provider=tts_provider,
                    tts_model=tts_model,
                )
                logger.info(
                    f"Adaptive behavior ({policy.mode}) enabled for session {session_id}"
                )

        engagement_processor = EngagementProcessor(
            session_id=session_id,
            db_session_factory=async_session_factory,
            transcript_state=transcript_state,
            language=language,
            notify_callback=notify_callback,
            config=engagement_config,
            signals=adaptive_signals,
        )
        logger.info(f"Engagement tracking enabled for session {session_id}")

    if pipeline_type == "voice_to_voice":
        task = await _build_v2v_pipeline(
            transport=transport,
            user_tap=user_tap,
            agent_tap=agent_tap,
            user_capture=user_capture,
            transcript_logger=transcript_logger,
            llm_model=llm_model,
            system_prompt=effective_prompt,
            welcome_message=welcome_message,
            language=language,
            max_duration_seconds=max_duration_seconds,
            voice=tts_voice,  # V2V pipelines use tts_voice for voice selection
            study_id=study_id,
            silence_timeout_seconds=silence_timeout_seconds,
            silence_prompt=silence_prompt,
        )
    else:
        task = await _build_modular_pipeline(
            transport=transport,
            user_tap=user_tap,
            agent_tap=agent_tap,
            user_capture=user_capture,
            transcript_logger=transcript_logger,
            llm_model=llm_model,
            system_prompt=effective_prompt,
            welcome_message=welcome_message,
            stt_provider=stt_provider,
            stt_model=stt_model,
            tts_provider=tts_provider,
            tts_model=tts_model,
            tts_voice=tts_voice,
            language=language,
            max_duration_seconds=max_duration_seconds,
            study_id=study_id,
            silence_timeout_seconds=silence_timeout_seconds,
            silence_prompt=silence_prompt,
            interview_mode=interview_mode,
            interview_guide=interview_guide,
            turn_detection=turn_detection,
            engagement_processor=engagement_processor,
            adaptive_processor=adaptive_processor,
            progress_callback=_progress_callback,
        )

    return task, audio_manager


# ── RAG tool registration ────────────────────────────────────────────────────

async def _study_has_knowledge(study_id: uuid.UUID) -> bool:
    """Check if a study actually has knowledge documents before registering RAG."""
    try:
        from sqlalchemy import select, func
        from app.models.knowledge import KnowledgeDocument

        async with async_session_factory() as db:
            result = await db.execute(
                select(func.count(KnowledgeDocument.id)).where(
                    KnowledgeDocument.study_id == study_id
                )
            )
            count = result.scalar() or 0
            return count > 0
    except Exception as e:
        logger.warning(f"Could not check knowledge documents for study={study_id}: {e}")
        return False


def _register_rag_tool(llm_service, study_id: uuid.UUID):
    """
    Register a 'search_knowledge_base' function on an LLM service.

    When the LLM invokes this tool, we perform a vector similarity search
    against the study's knowledge base (pgvector) and return the most
    relevant chunks as context.
    """

    async def search_knowledge_base(
        function_name: str,
        tool_call_id: str,
        args: dict,
        llm,
        context,
        result_callback,
    ):
        """Search the study's knowledge base for relevant context."""
        query = args.get("query", "")
        if not query:
            await result_callback("No query provided.")
            return

        try:
            from app.knowledge.embeddings import search_similar_chunks

            async with async_session_factory() as db:
                results = await search_similar_chunks(
                    db=db,
                    study_id=study_id,
                    query=query,
                    top_k=5,
                )

            if not results:
                await result_callback(
                    "No relevant information found in the knowledge base."
                )
                return

            # Format results as readable context
            context_parts = []
            for i, r in enumerate(results, 1):
                context_parts.append(
                    f"[Source: {r['title']}] (relevance: {r['similarity']})\n"
                    f"{r['content']}"
                )
            context_text = "\n\n---\n\n".join(context_parts)
            await result_callback(
                f"Knowledge base results:\n\n{context_text}"
            )

        except Exception as e:
            logger.exception(f"RAG search error: {e}")
            await result_callback(f"Error searching knowledge base: {e}")

    llm_service.register_function(
        "search_knowledge_base",
        search_knowledge_base,
    )

    logger.info(f"Registered RAG tool 'search_knowledge_base' for study={study_id}")


def _get_rag_tools_schema():
    """Return a ToolsSchema with the RAG search function definition."""
    from pipecat.adapters.schemas.function_schema import FunctionSchema
    from pipecat.adapters.schemas.tools_schema import ToolsSchema

    return ToolsSchema(
        standard_tools=[
            FunctionSchema(
                name="search_knowledge_base",
                description=(
                    "Search the study's knowledge base for relevant context, "
                    "background information, or specific instructions. Use this "
                    "when you need additional information to answer the "
                    "participant's question or to guide the conversation."
                ),
                properties={
                    "query": {
                        "type": "string",
                        "description": (
                            "The search query to find relevant information "
                            "in the knowledge base."
                        ),
                    },
                },
                required=["query"],
            )
        ]
    )


# ── Modular pipeline (STT → LLM → TTS) ──────────────────────────────────────

async def _build_llm(llm_model: str):
    """Instantiate the correct LLM service based on the model prefix.

    Supported prefixes (resolved in this order):
      - ``scaleway/<model>``   → OpenAI-compatible Scaleway endpoint
      - ``azure/<deployment>`` → Azure OpenAI via AsyncAzureOpenAI
      - ``gcp/<model>``        → Vertex AI OpenAI-compatible shim
      - ``anthropic/<model>``  → AnthropicLLMService (requires ANTHROPIC_API_KEY)
      - ``google/<model>``     → GoogleLLMService for text Gemini models
                                 (V2V Gemini Live is handled separately)
      - ``custom/<model>``     → OPENAI_COMPATIBLE_LLM_URL (LiteLLM proxy, vLLM)
      - everything else        → OpenAI (with optional ``openai/`` prefix stripped)
    """
    from pipecat.services.openai.llm import OpenAILLMService
    from pipecat.services.openai.base_llm import OpenAILLMSettings

    if llm_model.startswith("scaleway/"):
        model_name = llm_model[len("scaleway/"):]
        api_key = await _get_key("scaleway_secret_key")
        if not api_key:
            raise ValueError(
                "SCALEWAY_SECRET_KEY is not set. Add it to your .env file or dashboard."
            )
        return OpenAILLMService(
            api_key=api_key,
            base_url=settings.scaleway_api_url,
            settings=OpenAILLMSettings(model=model_name),
        )

    if llm_model.startswith("azure/"):
        model_name = llm_model[len("azure/"):]
        api_key = await _get_key("azure_openai_api_key")
        if not api_key:
            raise ValueError(
                "AZURE_OPENAI_API_KEY is not set. Add it to your .env file or dashboard."
            )
        from openai import AsyncAzureOpenAI
        client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )
        return OpenAILLMService(
            client=client,
            settings=OpenAILLMSettings(model=model_name),
        )

    if llm_model.startswith("gcp/"):
        model_name = llm_model[len("gcp/"):]
        gcp_project = await _get_key("gcp_project_id")
        if not gcp_project:
            raise ValueError(
                "GCP_PROJECT_ID is not set. Add it to your .env file or dashboard."
            )
        base_url = (
            f"https://{settings.gcp_location}-aiplatform.googleapis.com/v1/"
            f"projects/{gcp_project}/locations/{settings.gcp_location}/"
            f"publishers/google/models"
        )
        api_key = await _get_key("gcp_api_key") or "dummy"
        return OpenAILLMService(
            api_key=api_key,
            base_url=base_url,
            settings=OpenAILLMSettings(model=model_name),
        )

    if llm_model.startswith("anthropic/"):
        model_name = llm_model[len("anthropic/"):]
        api_key = await _get_key("anthropic_api_key")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env file or dashboard."
            )
        from pipecat.services.anthropic.llm import (
            AnthropicLLMService,
            AnthropicLLMSettings,
        )
        return AnthropicLLMService(
            api_key=api_key,
            settings=AnthropicLLMSettings(model=model_name),
        )

    if llm_model.startswith("google/"):
        # Modular pipelines using Gemini text models. (Gemini Live V2V is
        # handled by ``_build_gemini_live_pipeline``, not here.)
        model_name = llm_model[len("google/"):]
        api_key = await _get_key("google_api_key")
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY is not set. Add it to your .env file or dashboard."
            )
        from pipecat.services.google.llm import GoogleLLMService, GoogleLLMSettings
        return GoogleLLMService(
            api_key=api_key,
            settings=GoogleLLMSettings(model=model_name),
        )

    if llm_model.startswith("custom/"):
        # Generic OpenAI-compatible endpoint (LiteLLM proxy, vLLM, Ollama, etc.)
        model_name = llm_model[len("custom/"):]
        base_url = await _get_key("openai_compatible_llm_url") or settings.openai_compatible_llm_url
        if not base_url:
            raise ValueError(
                "OPENAI_COMPATIBLE_LLM_URL is not set. Provide a base URL "
                "(e.g. http://my-litellm:4000/v1) for your custom OpenAI-"
                "compatible endpoint, or pick a built-in provider."
            )
        api_key = await _get_key("openai_compatible_llm_api_key") or "not-needed"
        return OpenAILLMService(
            api_key=api_key,
            base_url=base_url,
            settings=OpenAILLMSettings(model=model_name),
        )

    # Default: OpenAI (strip optional "openai/" prefix)
    model_name = _resolve_model_name(llm_model)
    api_key = await _get_key("openai_api_key")
    eu_base_url = await _openai_base_url()
    if resolve_llm_api_kind(llm_model) == "responses":
        from pipecat.services.openai.responses.llm import (
            OpenAIResponsesHttpLLMService,
        )

        kwargs: dict = {
            "api_key": api_key,
            "settings": OpenAIResponsesHttpLLMService.Settings(
                model=model_name,
                max_completion_tokens=2048,
            ),
        }
        if eu_base_url:
            kwargs["base_url"] = eu_base_url
        return OpenAIResponsesHttpLLMService(**kwargs)

    kwargs: dict = {
        "api_key": api_key,
        "settings": OpenAILLMSettings(model=model_name),
    }
    if eu_base_url:
        kwargs["base_url"] = eu_base_url
    return OpenAILLMService(**kwargs)


async def _build_modular_pipeline(
    *,
    transport: FastAPIWebsocketTransport,
    user_tap: UserAudioTap,
    agent_tap: AgentAudioTap,
    user_capture: TranscriptUserCapture,
    transcript_logger: TranscriptLogger,
    llm_model: str,
    system_prompt: str,
    welcome_message: Optional[str],
    stt_provider: str,
    stt_model: Optional[str] = None,
    tts_provider: str,
    tts_model: Optional[str] = None,
    tts_voice: Optional[str],
    language: str,
    max_duration_seconds: Optional[int],
    study_id: Optional[uuid.UUID] = None,
    silence_timeout_seconds: Optional[int] = None,
    silence_prompt: Optional[str] = None,
    interview_mode: Optional[str] = None,
    interview_guide: Optional[dict] = None,
    turn_detection: Optional[str] = None,
    engagement_processor=None,
    adaptive_processor=None,
    progress_callback=None,
) -> PipelineTask:
    """Build the modular STT → LLM → TTS pipeline."""

    # ── STT ───────────────────────────────────────────────────
    stt = await _build_stt(stt_provider, language, stt_model)

    # ── LLM ───────────────────────────────────────────────────
    llm = await _build_llm(llm_model)

    # ── RAG tool registration (only if study has knowledge docs) ─
    tools = None
    if study_id and await _study_has_knowledge(study_id):
        _register_rag_tool(llm, study_id)
        tools = _get_rag_tools_schema()

    # Modern context API. VAD, turn detection and idle handling all hang off
    # the user aggregator now (pipecat 1.x).
    messages = [{"role": "system", "content": system_prompt}]
    if tools:
        context = LLMContext(messages=messages, tools=tools)
    else:
        context = LLMContext(messages=messages)
    context_aggregator = LLMContextAggregatorPair(
        context,
        user_params=_build_user_params(turn_detection, silence_timeout_seconds),
    )

    # ── TTS ───────────────────────────────────────────────────
    tts = await _build_tts(tts_provider, tts_voice, language, tts_model)

    # ── Silence handling ──────────────────────────────────────
    # The user aggregator fires on_user_turn_idle once per idle window (the
    # window is set via user_idle_timeout in _build_user_params). It re-arms
    # after the bot speaks again, so we cap the nudges to avoid pestering.
    if silence_timeout_seconds and silence_timeout_seconds > 0:
        _silence_msg = silence_prompt or "Take your time. Let me know when you're ready to continue."
        _idle_nudges = {"count": 0}

        @context_aggregator.user().event_handler("on_user_turn_idle")
        async def _on_user_idle(aggregator):
            if _idle_nudges["count"] >= 3:
                return
            _idle_nudges["count"] += 1
            logger.info(f"User idle (nudge #{_idle_nudges['count']}), sending silence prompt")
            await task.queue_frames([TTSSpeakFrame(text=_silence_msg)])

    # ── Structured interview guide processor (optional) ──────
    guide_processor = None
    guide_output_filter = None
    if interview_mode == "structured" and interview_guide:
        from app.pipeline.interview_guide import (
            InterviewGuideProcessor,
            StructuredOutputFilter,
        )
        guide_processor = InterviewGuideProcessor(interview_guide, language=language)
        guide_output_filter = StructuredOutputFilter(
            progress_callback=progress_callback,
            total_questions=guide_processor.total_questions,
        )
        logger.info(
            "Interview guide processor active "
            f"({guide_processor.total_questions} questions)"
        )

    # ── Pipeline wiring ───────────────────────────────────────
    # user_capture sits before the context aggregator to capture
    # TranscriptionFrame (user speech) before it's consumed.
    # transcript_logger sits after the LLM to capture TextFrame
    # (agent responses) as they stream downstream to TTS.
    #
    # CRITICAL: context_aggregator.assistant() must come AFTER
    # transport.output() so it can capture the bot's spoken text
    # (TextFrames from the LLM) and append them as ``assistant``
    # messages to the conversation context. Without it the model
    # never sees what it just said and ends up repeating itself
    # forever ("could you tell me about your background?" on every
    # turn). This was the root cause of the structured interview
    # appearing to "loop" — it was a context bug, not a guide bug.
    pipeline_nodes = [
        transport.input(),               # audio from browser
        user_tap,                        # optional per-turn user PCM capture
        stt,                             # speech → text
        user_capture,                    # log user transcriptions
        context_aggregator.user(),       # accumulate user turns
        llm,                             # text → LLM response
        transcript_logger,               # log agent text (TextFrame)
        tts,                             # text → speech
        agent_tap,                       # agent PCM + TTSStopped (right after TTS)
        transport.output(),              # audio back to browser
        context_aggregator.assistant(),  # accumulate bot turns
    ]

    # Insert guide processor right after user_capture so it observes
    # UserStoppedSpeakingFrame and pushes LLMMessagesAppendFrame *before*
    # the user context aggregator triggers the next LLM run.
    if guide_processor:
        insert_at = pipeline_nodes.index(user_capture) + 1
        pipeline_nodes.insert(insert_at, guide_processor)

    # The structured output filter enforces one-question-per-turn on the
    # LLM's streamed text. It sits directly after the LLM and BEFORE the
    # transcript logger, so persisted transcripts (and the assistant context
    # downstream) match what the participant actually hears.
    if guide_output_filter:
        pipeline_nodes.insert(pipeline_nodes.index(llm) + 1, guide_output_filter)

    # Engagement processor sits right after user_capture (observe-only). It
    # reads the freshly-assigned transcript sequence and never blocks frames.
    if engagement_processor:
        insert_at = pipeline_nodes.index(user_capture) + 1
        pipeline_nodes.insert(insert_at, engagement_processor)

    # Adaptive processor sits right after the engagement processor so it can
    # read this turn's signals and inject before the user context aggregator.
    if adaptive_processor and engagement_processor:
        insert_at = pipeline_nodes.index(engagement_processor) + 1
        pipeline_nodes.insert(insert_at, adaptive_processor)

    pipeline = Pipeline(pipeline_nodes)

    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True),
    )

    # ── Welcome message (spoken by TTS on connect) ────────────
    @transport.event_handler("on_client_connected")
    async def _on_connected(transport_ref, ws):
        if welcome_message:
            # TTSSpeakFrame bypasses text-aggregation so the greeting is
            # spoken immediately instead of being buffered.
            await task.queue_frames(
                [TTSSpeakFrame(text=welcome_message)]
            )
        else:
            # No explicit welcome message — push the context to trigger the
            # LLM to generate a greeting from the system prompt.
            await task.queue_frames(
                [LLMContextFrame(context=context)]
            )

    # ── Client disconnect → shut down pipeline ────────────────
    @transport.event_handler("on_client_disconnected")
    async def _on_disconnected(transport_ref, ws):
        logger.info("Client disconnected — ending modular pipeline")
        await task.queue_frames([EndFrame()])

    # ── Session timeout ───────────────────────────────────────
    if max_duration_seconds:
        @transport.event_handler("on_session_timeout")
        async def _on_timeout(transport_ref, ws):
            logger.info("Session timeout — ending modular pipeline")
            await task.queue_frames([EndFrame()])

    return task


# ── Voice-to-Voice pipeline dispatcher ──────────────────────────────────────

async def _build_v2v_pipeline(
    *,
    transport: FastAPIWebsocketTransport,
    user_tap: UserAudioTap,
    agent_tap: AgentAudioTap,
    user_capture: TranscriptUserCapture,
    transcript_logger: TranscriptLogger,
    llm_model: str,
    system_prompt: str,
    welcome_message: Optional[str],
    language: str,
    max_duration_seconds: Optional[int],
    silence_timeout_seconds: Optional[int] = None,
    silence_prompt: Optional[str] = None,
    voice: Optional[str] = None,
    study_id: Optional[uuid.UUID] = None,
) -> PipelineTask:
    """Dispatch to the correct V2V backend based on the model prefix."""
    if llm_model.startswith("google/"):
        return await _build_gemini_live_pipeline(
            transport=transport,
            user_tap=user_tap,
            agent_tap=agent_tap,
            user_capture=user_capture,
            transcript_logger=transcript_logger,
            llm_model=llm_model,
            system_prompt=system_prompt,
            welcome_message=welcome_message,
            language=language,
            max_duration_seconds=max_duration_seconds,
            voice=voice or "Charon",
            study_id=study_id,
            silence_timeout_seconds=silence_timeout_seconds,
            silence_prompt=silence_prompt,
        )
    # Default: OpenAI Realtime
    return await _build_openai_realtime_pipeline(
        transport=transport,
        user_tap=user_tap,
        agent_tap=agent_tap,
        user_capture=user_capture,
        transcript_logger=transcript_logger,
        llm_model=llm_model,
        system_prompt=system_prompt,
        welcome_message=welcome_message,
        language=language,
        max_duration_seconds=max_duration_seconds,
        voice=voice or "coral",
        study_id=study_id,
        silence_timeout_seconds=silence_timeout_seconds,
        silence_prompt=silence_prompt,
    )


async def _build_openai_realtime_pipeline(
    *,
    transport: FastAPIWebsocketTransport,
    user_tap: UserAudioTap,
    agent_tap: AgentAudioTap,
    user_capture: TranscriptUserCapture,
    transcript_logger: TranscriptLogger,
    llm_model: str,
    system_prompt: str,
    welcome_message: Optional[str],
    language: str,
    max_duration_seconds: Optional[int],
    voice: str = "coral",
    study_id: Optional[uuid.UUID] = None,
    silence_timeout_seconds: Optional[int] = None,
    silence_prompt: Optional[str] = None,
) -> PipelineTask:
    """Build the voice-to-voice pipeline using OpenAI Realtime API.

    Key differences from the modular pipeline:
    - NO context aggregator — the Realtime API manages its own context
    - Audio frames flow directly: transport → Realtime LLM → transport
    - The Realtime service connects to OpenAI's WebSocket and handles
      VAD, transcription, and audio generation internally
    - We push LLMMessagesFrame on connect to set initial context and
      trigger the first greeting response
    """
    from pipecat.services.openai.realtime.llm import (
        OpenAIRealtimeLLMService,
        OpenAIRealtimeLLMSettings,
    )
    from pipecat.services.openai.realtime.events import (
        SessionProperties,
        AudioConfiguration,
        AudioInput,
        AudioOutput,
        InputAudioTranscription,
        TurnDetection,
    )

    model_name = _resolve_model_name(llm_model)
    logger.info(f"Building OpenAI Realtime pipeline with model={model_name}, voice={voice}")

    effective_system_prompt = _v2v_system_prompt_with_welcome(
        system_prompt, welcome_message
    )

    # The OpenAI Realtime API (2025+) requires output_modalities to be
    # EITHER ["text"] or ["audio"], NOT ["text", "audio"] combined.
    # Voice is configured under audio.output.voice.
    #
    # TODO: gpt-realtime-2 supports a `reasoning_effort` parameter
    # (low/medium/high). We don't pass it through yet because pipecat's
    # SessionProperties doesn't expose the field and we'd need a brittle
    # subclass to inject it. The model still works without it (uses OpenAI's
    # default). Revisit once pipecat ships official support.
    api_key = await _get_key("openai_api_key")
    realtime_base_url = await _openai_realtime_base_url()
    realtime_llm = OpenAIRealtimeLLMService(
        api_key=api_key,
        base_url=realtime_base_url,
        settings=OpenAIRealtimeLLMSettings(
            model=model_name,
            system_instruction=effective_system_prompt,
            session_properties=SessionProperties(
                output_modalities=["audio"],
                audio=AudioConfiguration(
                    input=AudioInput(
                        transcription=InputAudioTranscription(
                            language=language[:2] if language else None,
                        ),
                        turn_detection=TurnDetection(),
                    ),
                    output=AudioOutput(voice=voice),
                ),
            ),
        ),
    )

    # ── RAG tool registration (only if study has knowledge docs) ─
    if study_id and await _study_has_knowledge(study_id):
        _register_rag_tool(realtime_llm, study_id)

    # V2V pipeline: NO context aggregator needed.
    # The Realtime service handles context management internally.
    # Both user_capture and transcript_logger sit after the Realtime LLM
    # because it emits TranscriptionFrame (user) and TextFrame (agent)
    # downstream.
    # user_capture MUST sit before Realtime: user TranscriptionFrames are
    # pushed UPSTREAM from the Realtime service, not downstream.
    nodes = [
        transport.input(),
        user_tap,
        user_capture,
        realtime_llm,
        agent_tap,
        transcript_logger,
        transport.output(),
    ]

    pipeline = Pipeline(nodes)

    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True),
    )

    # ── Initial context + greeting on connect ─────────────────
    # Push LLMContextFrame so the Realtime service sets up the
    # conversation context (system prompt) and generates the first
    # response. The welcome message is already baked into
    # ``effective_system_prompt`` as a "say verbatim" directive, so the
    # model opens with it on its own turn instead of treating it as a
    # user utterance.
    # NOTE: LLMContextFrame (not LLMMessagesFrame) is required because
    # OpenAIRealtimeLLMService.process_frame only handles LLMContextFrame.
    @transport.event_handler("on_client_connected")
    async def _on_connected(transport_ref, ws):
        logger.info("V2V client connected — pushing initial context")
        messages = [{"role": "system", "content": effective_system_prompt}]
        context = LLMContext(messages=messages)
        await task.queue_frames(
            [LLMContextFrame(context=context)]
        )

    # ── Client disconnect → shut down pipeline ────────────────
    @transport.event_handler("on_client_disconnected")
    async def _on_disconnected(transport_ref, ws):
        logger.info("Client disconnected — ending OpenAI Realtime pipeline")
        await task.queue_frames([EndFrame()])

    if max_duration_seconds:
        @transport.event_handler("on_session_timeout")
        async def _on_timeout(transport_ref, ws):
            logger.info("Session timeout — ending OpenAI Realtime pipeline")
            await task.queue_frames([EndFrame()])

    return task


async def _build_gemini_live_pipeline(
    *,
    transport: FastAPIWebsocketTransport,
    user_tap: UserAudioTap,
    agent_tap: AgentAudioTap,
    user_capture: TranscriptUserCapture,
    transcript_logger: TranscriptLogger,
    llm_model: str,
    system_prompt: str,
    welcome_message: Optional[str],
    language: str,
    max_duration_seconds: Optional[int],
    voice: str = "Charon",
    study_id: Optional[uuid.UUID] = None,
    silence_timeout_seconds: Optional[int] = None,
    silence_prompt: Optional[str] = None,
) -> PipelineTask:
    """Build the voice-to-voice pipeline using Google Gemini Live native audio."""
    try:
        from pipecat.services.google.gemini_live.llm import (
            GeminiLiveLLMService,
            GeminiLiveLLMSettings,
        )
    except ImportError:
        raise ImportError(
            "Gemini Live support requires the google-genai package. "
            "Install it with: pip install pipecat-ai[google]"
        )

    # Strip "google/" prefix to get the actual model name
    model_name = llm_model[len("google/"):]

    api_key = await _get_key("google_api_key")
    if not api_key:
        raise ValueError(
            "GOOGLE_API_KEY is not set. Add it to .env or dashboard settings."
        )

    logger.info(f"Building Gemini Live pipeline with model=models/{model_name}, voice={voice}")

    effective_system_prompt = _v2v_system_prompt_with_welcome(
        system_prompt, welcome_message
    )

    gemini_llm = GeminiLiveLLMService(
        api_key=api_key,
        settings=GeminiLiveLLMSettings(
            model=f"models/{model_name}",
            system_instruction=effective_system_prompt,
            voice=voice,
        ),
    )

    # ── RAG tool registration (only if study has knowledge docs) ─
    if study_id and await _study_has_knowledge(study_id):
        _register_rag_tool(gemini_llm, study_id)

    # user_capture before Gemini Live (same UPSTREAM transcription as OpenAI RT).
    nodes = [
        transport.input(),
        user_tap,
        user_capture,
        gemini_llm,
        agent_tap,
        transcript_logger,
        transport.output(),
    ]

    pipeline = Pipeline(nodes)

    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True),
    )

    # ── Initial context + greeting on connect ─────────────────
    # Welcome message is baked into ``effective_system_prompt`` as a
    # "say verbatim" directive, so the model opens with it on its own
    # turn instead of being treated as user input.
    @transport.event_handler("on_client_connected")
    async def _on_connected(transport_ref, ws):
        logger.info("Gemini Live client connected — pushing initial context")
        messages = [{"role": "system", "content": effective_system_prompt}]
        context = LLMContext(messages=messages)
        await task.queue_frames(
            [LLMContextFrame(context=context)]
        )

    @transport.event_handler("on_client_disconnected")
    async def _on_disconnected(transport_ref, ws):
        logger.info("Client disconnected — ending Gemini Live pipeline")
        await task.queue_frames([EndFrame()])

    if max_duration_seconds:
        @transport.event_handler("on_session_timeout")
        async def _on_timeout(transport_ref, ws):
            logger.info("Session timeout — ending Gemini Live pipeline")
            await task.queue_frames([EndFrame()])

    return task


# ── Protobuf serializer with TTS frame support ──────────────────────────────

def _build_serializer() -> ProtobufFrameSerializer:
    """
    Create a ProtobufFrameSerializer that knows about all audio frame
    sub-types produced by TTS services.

    Pipecat's default serializer only recognises OutputAudioRawFrame by
    *exact* type match (no isinstance).  TTS services like ElevenLabs emit
    TTSAudioRawFrame which is a subclass and would be silently dropped
    unless we register it here.
    """
    serializer = ProtobufFrameSerializer()

    from pipecat.frames.frames import TTSAudioRawFrame
    serializer.SERIALIZABLE_TYPES[TTSAudioRawFrame] = "audio"

    try:
        from pipecat.frames.frames import SpeechOutputAudioRawFrame
        serializer.SERIALIZABLE_TYPES[SpeechOutputAudioRawFrame] = "audio"
    except ImportError:
        pass

    return serializer


# ── Factory helpers ──────────────────────────────────────────────────────────

def _resolve_model_name(llm_model: str) -> str:
    """
    Strip LiteLLM provider prefix if present.
    e.g. 'openai/gpt-4o-mini' → 'gpt-4o-mini'
    """
    if "/" in llm_model:
        return llm_model.split("/", 1)[1]
    return llm_model


def _get_vad():
    """Return a Silero VAD analyzer instance."""
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    return SileroVADAnalyzer()


def _build_turn_analyzer(turn_detection: Optional[str]):
    """Return the smart-turn analyzer for the modular pipeline.

    "local" (default) runs the bundled smart-turn-v3 ONNX model on-device.
    "remote" sends audio to the HTTP endpoint in SMART_TURN_REMOTE_URL; if that
    isn't set we fall back to local so a misconfigured agent still works.
    """
    from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import (
        LocalSmartTurnAnalyzerV3,
    )

    if (turn_detection or "local").lower() == "remote":
        url = (settings.smart_turn_remote_url or "").strip()
        if url:
            import aiohttp
            from pipecat.audio.turn.smart_turn.http_smart_turn import (
                HttpSmartTurnAnalyzer,
            )

            headers = {}
            if settings.smart_turn_remote_api_key:
                headers["Authorization"] = f"Bearer {settings.smart_turn_remote_api_key}"
            # The session lives for the pipeline's lifetime; pipecat closes it
            # on shutdown along with the analyzer.
            session = aiohttp.ClientSession()
            logger.info(f"Turn detection: remote smart-turn ({url})")
            return HttpSmartTurnAnalyzer(
                url=url,
                aiohttp_session=session,
                headers=headers or None,
            )
        logger.warning(
            "turn_detection=remote but SMART_TURN_REMOTE_URL is empty; "
            "using the local smart-turn model instead"
        )

    logger.info("Turn detection: local smart-turn model")
    return LocalSmartTurnAnalyzerV3()


def _build_user_params(
    turn_detection: Optional[str],
    user_idle_timeout_seconds: Optional[int],
) -> LLMUserAggregatorParams:
    """Build the user-aggregator params (VAD + turn strategies + idle).

    Pipecat 1.x moved all of this off the transport and onto the user
    aggregator. VAD detects speech; the turn analyzer decides when the user is
    actually done talking.
    """
    from pipecat.turns.user_turn_strategies import UserTurnStrategies
    from pipecat.turns.user_start import (
        VADUserTurnStartStrategy,
        TranscriptionUserTurnStartStrategy,
    )
    from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy

    idle = (
        float(user_idle_timeout_seconds)
        if user_idle_timeout_seconds and user_idle_timeout_seconds > 0
        else 0
    )
    return LLMUserAggregatorParams(
        vad_analyzer=_get_vad(),
        user_turn_strategies=UserTurnStrategies(
            start=[
                VADUserTurnStartStrategy(),
                TranscriptionUserTurnStartStrategy(),
            ],
            stop=[
                TurnAnalyzerUserTurnStopStrategy(
                    turn_analyzer=_build_turn_analyzer(turn_detection)
                ),
            ],
        ),
        user_idle_timeout=idle,
    )


async def _build_stt(provider: str, language: str, model: Optional[str] = None):
    """Instantiate the correct STT service based on the agent config.

    The optional ``model`` argument is forwarded to the underlying pipecat
    service when supported (Deepgram, OpenAI, self-hosted). Scaleway is
    pinned to ``whisper-large-v3`` because that is the only model they
    expose. Azure ignores the model (pipecat reads from env).
    """
    provider = provider.lower()

    if provider == "deepgram":
        # deepgram-sdk v4+ removed the top-level LiveOptions export; Pipecat
        # 0.0.105+ takes a DeepgramSTTSettings object instead.
        from pipecat.services.deepgram.stt import (
            DeepgramSTTService,
            DeepgramSTTSettings,
        )
        api_key = await _get_key("deepgram_api_key")
        settings_kwargs: dict = {}
        if model:
            settings_kwargs["model"] = model
        if language:
            settings_kwargs["language"] = language
        kwargs = {"api_key": api_key}
        if settings_kwargs:
            kwargs["settings"] = DeepgramSTTSettings(**settings_kwargs)
        return DeepgramSTTService(**kwargs)

    if provider in ("whisper", "openai"):
        api_key = await _get_key("openai_api_key")
        if model == "gpt-realtime-whisper":
            from pipecat.services.openai.stt import OpenAIRealtimeSTTService

            # Local VAD commits turns for realtime transcription.
            return OpenAIRealtimeSTTService(
                api_key=api_key,
                base_url=await _openai_realtime_base_url(),
                turn_detection=False,
                settings=OpenAIRealtimeSTTService.Settings(
                    model=model,
                    language=language,
                ),
            )

        from pipecat.services.openai.stt import OpenAISTTService, OpenAISTTSettings

        kwargs = {"api_key": api_key, "language": language}
        if model:
            kwargs["settings"] = OpenAISTTSettings(model=model)
        eu_base_url = await _openai_base_url()
        if eu_base_url:
            kwargs["base_url"] = eu_base_url
        return OpenAISTTService(**kwargs)

    if provider == "scaleway":
        from pipecat.services.openai.stt import OpenAISTTService, OpenAISTTSettings
        api_key = await _get_key("scaleway_secret_key")
        if not api_key:
            raise ValueError(
                "SCALEWAY_SECRET_KEY is not set. Required for Scaleway STT."
            )
        return OpenAISTTService(
            api_key=api_key,
            base_url=settings.scaleway_api_url,
            language=language,
            settings=OpenAISTTSettings(model=model or "whisper-large-v3"),
        )

    if provider == "azure":
        from pipecat.services.azure.stt import AzureSTTService
        return AzureSTTService()

    if provider == "self_hosted":
        from pipecat.services.openai.stt import OpenAISTTService, OpenAISTTSettings
        base_url = await _get_key("self_hosted_stt_url") or settings.self_hosted_stt_url
        if not base_url:
            raise ValueError(
                "SELF_HOSTED_STT_URL is not set. Provide the base URL for your "
                "OpenAI-compatible STT server (e.g. http://my-server:8000/v1)."
            )
        api_key = await _get_key("self_hosted_stt_api_key") or "not-needed"
        # Per-agent model wins over global default
        effective_model = model or settings.self_hosted_stt_model or "whisper-1"
        return OpenAISTTService(
            api_key=api_key,
            base_url=base_url,
            language=language,
            settings=OpenAISTTSettings(model=effective_model),
        )

    raise ValueError(f"Unsupported STT provider: {provider}")


async def _build_tts(
    provider: str,
    voice: Optional[str],
    language: str,
    model: Optional[str] = None,
):
    """Instantiate the correct TTS service based on the agent config.

    The optional ``model`` argument is forwarded to the underlying pipecat
    service when the provider supports model selection (OpenAI, self-hosted).
    ElevenLabs/Cartesia/Azure pin model-equivalent behaviour via voice IDs.
    """
    provider = provider.lower()

    if provider == "elevenlabs":
        from pipecat.services.elevenlabs.tts import (
            ElevenLabsTTSService,
            ElevenLabsTTSSettings,
        )
        resolved_voice = _resolve_elevenlabs_voice(voice)
        api_key = await _get_key("elevenlabs_api_key")
        return ElevenLabsTTSService(
            api_key=api_key,
            settings=ElevenLabsTTSSettings(voice=resolved_voice),
        )

    if provider == "openai":
        from pipecat.services.openai.tts import OpenAITTSService, OpenAITTSSettings
        api_key = await _get_key("openai_api_key")
        eu_base_url = await _openai_base_url()
        kwargs: dict = {
            "api_key": api_key,
            "settings": OpenAITTSSettings(
                model=model or "gpt-4o-mini-tts",
                voice=voice or "alloy",
            ),
        }
        if eu_base_url:
            kwargs["base_url"] = eu_base_url
        return OpenAITTSService(**kwargs)

    if provider == "cartesia":
        from pipecat.services.cartesia.tts import CartesiaTTSService
        api_key = await _get_key("cartesia_api_key")
        if not api_key:
            raise ValueError("Cartesia API key is not set (CARTESIA_API_KEY)")
        return CartesiaTTSService(
            api_key=api_key,
            voice_id=voice or "a0e99841-438c-4a64-b679-ae501e7d6091",
        )

    if provider == "azure":
        from pipecat.services.azure.tts import AzureTTSService
        return AzureTTSService()

    if provider == "self_hosted":
        from pipecat.services.openai.tts import OpenAITTSService, OpenAITTSSettings
        base_url = await _get_key("self_hosted_tts_url") or settings.self_hosted_tts_url
        if not base_url:
            raise ValueError(
                "SELF_HOSTED_TTS_URL is not set. Provide the base URL for your "
                "OpenAI-compatible TTS server (e.g. http://my-server:8100/v1)."
            )
        api_key = await _get_key("self_hosted_tts_api_key") or "not-needed"
        # Per-agent model wins over global default
        effective_model = model or settings.self_hosted_tts_model or "tts-1"
        return OpenAITTSService(
            api_key=api_key,
            base_url=base_url,
            settings=OpenAITTSSettings(
                model=effective_model,
                voice=voice or "alloy",
            ),
        )

    raise ValueError(f"Unsupported TTS provider: {provider}")


# ── ElevenLabs voice name → ID mapping ──────────────────────────────────────
# Common default voices — users can also paste the actual voice ID directly.
_ELEVENLABS_VOICES = {
    "rachel": "21m00Tcm4TlvDq8ikWAM",
    "domi": "AZnzlk1XvdvUeBnXmlld",
    "bella": "EXAVITQu4vr4xnSDxMaL",
    "antoni": "ErXwobaYiN019PkySvjV",
    "elli": "MF3mGyEYCl7XYWbV9V6O",
    "josh": "TxGEqnHWrfWFTfGW9XjX",
    "arnold": "VR6AewLTigWG4xSOukaG",
    "adam": "pNInz6obpgDQGcFmaJgB",
    "sam": "yoZ06aMxZJJ28mfd3POQ",
    "charlie": "IKne3meq5aSn9XLyUdCD",
    "emily": "LcfcDJNUP1GQjkzn1xUU",
    "alice": "Xb7hH8MSUJpSbSDYk0k2",
    "bill": "pqHfZKP75CvOlQylNhV4",
    "george": "JBFqnCBsd6RMkjVDRZzb",
    "lily": "pFZP5JQG7iQjIQuC4Bku",
    "sarah": "EXAVITQu4vr4xnSDxMaL",
    "chris": "iP95p4xoKVk53GoZ742B",
}


def _resolve_elevenlabs_voice(voice: Optional[str]) -> str:
    """
    Resolve a voice name or ID to an ElevenLabs voice ID.
    Accepts either a friendly name (e.g. 'rachel') or a raw voice ID.
    Falls back to Rachel's voice ID if nothing is provided.
    """
    if not voice:
        return "21m00Tcm4TlvDq8ikWAM"  # Rachel default

    # Check if it's a known friendly name (case-insensitive)
    lower = voice.strip().lower()
    if lower in _ELEVENLABS_VOICES:
        return _ELEVENLABS_VOICES[lower]

    # Assume it's a raw voice ID
    return voice
