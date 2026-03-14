"""
SURVEYOR — Pipecat pipeline builder (pipecat 0.0.105).

Supports two pipeline types:

  Modular:
    Transport(in) → STT → TranscriptLogger → UserCtx → LLM → TTS → Transport(out)

  Voice-to-Voice:
    OpenAI Realtime:   Transport(in) → OpenAIRealtimeLLM → TranscriptLogger → Transport(out)
    Gemini Live:       Transport(in) → GeminiLiveLLM → TranscriptLogger → Transport(out)

Uses the *modern* pipecat 0.0.105 API:
  - LLMContext  (not the deprecated OpenAILLMContext)
  - LLMContextAggregatorPair  (not llm.create_context_aggregator)
  - Settings dataclasses  (not deprecated keyword args)
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
    LLMMessagesFrame,
    TTSSpeakFrame,
)

# Modern context API — NOT the deprecated OpenAILLMContext
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)

from app.config import settings
from app.database import async_session_factory
from app.pipeline.transcript_logger import TranscriptLogger


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


async def build_twilio_pipeline(
    *,
    websocket,
    session_id: uuid.UUID,
    system_prompt: str,
    welcome_message: Optional[str],
    pipeline_type: str = "modular",
    llm_model: str,
    stt_provider: str = "deepgram",
    tts_provider: str = "elevenlabs",
    tts_voice: Optional[str] = None,
    language: str = "en",
    max_duration_seconds: Optional[int] = None,
    notify_callback=None,
    stream_sid: str = "",
    call_sid: Optional[str] = None,
    study_id: Optional[uuid.UUID] = None,
    interview_mode: Optional[str] = None,
    interview_guide: Optional[dict] = None,
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
            vad_enabled=True,
            vad_analyzer=_get_vad(),
            vad_audio_passthrough=True,
            serializer=serializer,
            session_timeout=max_duration_seconds,
        ),
    )

    transcript_logger = TranscriptLogger(
        session_id=session_id,
        db_session_factory=async_session_factory,
        notify_callback=notify_callback,
    )

    # Twilio calls always use the modular pipeline (STT → LLM → TTS)
    # because the telephony audio is 8kHz μ-law, not suitable for
    # direct V2V endpoints which expect higher-quality audio.
    # However, if the agent is configured for V2V, we still support it.
    if pipeline_type == "voice_to_voice":
        task = await _build_v2v_pipeline(
            transport=transport,
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
            transcript_logger=transcript_logger,
            llm_model=llm_model,
            system_prompt=effective_prompt,
            welcome_message=welcome_message,
            stt_provider=stt_provider,
            tts_provider=tts_provider,
            tts_voice=tts_voice,
            language=language,
            max_duration_seconds=max_duration_seconds,
            study_id=study_id,
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
    tts_provider: str = "elevenlabs",
    tts_voice: Optional[str] = None,
    language: str = "en",
    max_duration_seconds: Optional[int] = None,
    notify_callback=None,
    study_id: Optional[uuid.UUID] = None,
    silence_timeout_seconds: Optional[int] = None,
    silence_prompt: Optional[str] = None,
    interview_mode: Optional[str] = None,
    interview_guide: Optional[dict] = None,
) -> PipelineTask:
    """
    Build and return a ready-to-run PipelineTask.
    The caller only needs to `await runner.run(task)`.
    """

    # ── Structured interview prompt enhancement ───────────────────
    effective_prompt = system_prompt
    if interview_mode == "structured" and interview_guide:
        from app.pipeline.interview_guide import build_structured_prompt
        effective_prompt = build_structured_prompt(system_prompt, interview_guide)
        logger.info(
            f"Structured interview mode: {len(interview_guide.get('questions', []))} questions loaded"
        )

    # ── Transport (WebSocket ↔ browser) ───────────────────────────
    serializer = _build_serializer()

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            vad_enabled=True,
            vad_analyzer=_get_vad(),
            vad_audio_passthrough=True,
            serializer=serializer,
            session_timeout=max_duration_seconds,
        ),
    )

    # ── Transcript logger ──────────────────────────────────────────
    transcript_logger = TranscriptLogger(
        session_id=session_id,
        db_session_factory=async_session_factory,
        notify_callback=notify_callback,
    )

    if pipeline_type == "voice_to_voice":
        task = await _build_v2v_pipeline(
            transport=transport,
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
            transcript_logger=transcript_logger,
            llm_model=llm_model,
            system_prompt=effective_prompt,
            welcome_message=welcome_message,
            stt_provider=stt_provider,
            tts_provider=tts_provider,
            tts_voice=tts_voice,
            language=language,
            max_duration_seconds=max_duration_seconds,
            study_id=study_id,
            silence_timeout_seconds=silence_timeout_seconds,
            silence_prompt=silence_prompt,
        )

    return task


# ── RAG tool registration ────────────────────────────────────────────────────

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
    """Instantiate the correct LLM service based on the model prefix."""
    from pipecat.services.openai.llm import OpenAILLMService, OpenAILLMSettings

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

    # Default: OpenAI (strip optional "openai/" prefix)
    model_name = _resolve_model_name(llm_model)
    api_key = await _get_key("openai_api_key")
    return OpenAILLMService(
        api_key=api_key,
        settings=OpenAILLMSettings(model=model_name),
    )


async def _build_modular_pipeline(
    *,
    transport: FastAPIWebsocketTransport,
    transcript_logger: TranscriptLogger,
    llm_model: str,
    system_prompt: str,
    welcome_message: Optional[str],
    stt_provider: str,
    tts_provider: str,
    tts_voice: Optional[str],
    language: str,
    max_duration_seconds: Optional[int],
    study_id: Optional[uuid.UUID] = None,
    silence_timeout_seconds: Optional[int] = None,
    silence_prompt: Optional[str] = None,
) -> PipelineTask:
    """Build the modular STT → LLM → TTS pipeline."""

    # ── STT ───────────────────────────────────────────────────
    stt = await _build_stt(stt_provider, language)

    # ── LLM ───────────────────────────────────────────────────
    llm = await _build_llm(llm_model)

    # ── RAG tool registration ─────────────────────────────────
    tools = None
    if study_id:
        _register_rag_tool(llm, study_id)
        tools = _get_rag_tools_schema()

    # Modern context API
    messages = [{"role": "system", "content": system_prompt}]
    if tools:
        context = LLMContext(messages=messages, tools=tools)
    else:
        context = LLMContext(messages=messages)
    context_aggregator = LLMContextAggregatorPair(context=context)

    # ── TTS ───────────────────────────────────────────────────
    tts = await _build_tts(tts_provider, tts_voice, language)

    # ── Silence handling (UserIdleProcessor) ─────────────────
    idle_processor = None
    if silence_timeout_seconds and silence_timeout_seconds > 0:
        from pipecat.processors.user_idle_processor import UserIdleProcessor
        import warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning, module="pipecat.processors.user_idle_processor")

        _silence_msg = silence_prompt or "Take your time. Let me know when you're ready to continue."

        async def _handle_user_idle(processor: "UserIdleProcessor", retry_count: int) -> bool:
            logger.info(f"User idle (retry #{retry_count}), sending silence prompt")
            await task.queue_frames([TTSSpeakFrame(text=_silence_msg)])
            return retry_count < 3  # stop after 3 retries

        idle_processor = UserIdleProcessor(
            callback=_handle_user_idle,
            timeout=float(silence_timeout_seconds),
        )

    # ── Pipeline wiring ───────────────────────────────────────
    pipeline_nodes = [
        transport.input(),          # audio from browser
        stt,                        # speech → text
        transcript_logger,          # log user transcript + agent text
        context_aggregator.user(),  # accumulate user turns
        llm,                        # text → LLM response
        tts,                        # text → speech
        transport.output(),         # audio back to browser
    ]

    # Insert idle processor after STT (before user context aggregator)
    if idle_processor:
        pipeline_nodes.insert(3, idle_processor)  # after transcript_logger, before context_aggregator.user()

    pipeline = Pipeline(pipeline_nodes)

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
        ),
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
            # No explicit welcome message — trigger the LLM to generate
            # a greeting from the system prompt.
            await task.queue_frames(
                [LLMMessagesFrame(messages=messages)]
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
            transcript_logger=transcript_logger,
            llm_model=llm_model,
            system_prompt=system_prompt,
            welcome_message=welcome_message,
            language=language,
            max_duration_seconds=max_duration_seconds,
            voice=voice or "Charon",
            study_id=study_id,
        )
    # Default: OpenAI Realtime
    return await _build_openai_realtime_pipeline(
        transport=transport,
        transcript_logger=transcript_logger,
        llm_model=llm_model,
        system_prompt=system_prompt,
        welcome_message=welcome_message,
        language=language,
        max_duration_seconds=max_duration_seconds,
        voice=voice or "coral",
        study_id=study_id,
    )


async def _build_openai_realtime_pipeline(
    *,
    transport: FastAPIWebsocketTransport,
    transcript_logger: TranscriptLogger,
    llm_model: str,
    system_prompt: str,
    welcome_message: Optional[str],
    language: str,
    max_duration_seconds: Optional[int],
    voice: str = "coral",
    study_id: Optional[uuid.UUID] = None,
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
        AudioOutput,
    )

    model_name = _resolve_model_name(llm_model)
    logger.info(f"Building OpenAI Realtime pipeline with model={model_name}, voice={voice}")

    # The OpenAI Realtime API (2025+) requires output_modalities to be
    # EITHER ["text"] or ["audio"], NOT ["text", "audio"] combined.
    # Voice is configured under audio.output.voice.
    api_key = await _get_key("openai_api_key")
    realtime_llm = OpenAIRealtimeLLMService(
        api_key=api_key,
        settings=OpenAIRealtimeLLMSettings(
            model=model_name,
            system_instruction=system_prompt,
            session_properties=SessionProperties(
                output_modalities=["audio"],
                audio=AudioConfiguration(
                    output=AudioOutput(voice=voice),
                ),
            ),
        ),
    )

    # ── RAG tool registration ─────────────────────────────────
    if study_id:
        _register_rag_tool(realtime_llm, study_id)

    # V2V pipeline: NO context aggregator needed.
    # The Realtime service handles context management internally.
    pipeline = Pipeline(
        [
            transport.input(),
            realtime_llm,
            transcript_logger,
            transport.output(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True, enable_metrics=True),
    )

    # ── Initial context + greeting on connect ─────────────────
    # Push LLMContextFrame so the Realtime service sets up the
    # conversation context (system prompt) and generates a greeting.
    # NOTE: LLMContextFrame (not LLMMessagesFrame) is required because
    # OpenAIRealtimeLLMService.process_frame only handles LLMContextFrame.
    @transport.event_handler("on_client_connected")
    async def _on_connected(transport_ref, ws):
        logger.info("V2V client connected — pushing initial context")
        messages = [{"role": "system", "content": system_prompt}]
        if welcome_message:
            # Add a user message that prompts the agent to greet
            messages.append(
                {"role": "user", "content": welcome_message}
            )
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
    transcript_logger: TranscriptLogger,
    llm_model: str,
    system_prompt: str,
    welcome_message: Optional[str],
    language: str,
    max_duration_seconds: Optional[int],
    voice: str = "Charon",
    study_id: Optional[uuid.UUID] = None,
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

    gemini_llm = GeminiLiveLLMService(
        api_key=api_key,
        settings=GeminiLiveLLMSettings(
            model=f"models/{model_name}",
            system_instruction=system_prompt,
            voice=voice,
        ),
    )

    # ── RAG tool registration ─────────────────────────────────
    if study_id:
        _register_rag_tool(gemini_llm, study_id)

    # V2V pipeline: NO context aggregator needed.
    pipeline = Pipeline(
        [
            transport.input(),
            gemini_llm,
            transcript_logger,
            transport.output(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True, enable_metrics=True),
    )

    # ── Initial context + greeting on connect ─────────────────
    @transport.event_handler("on_client_connected")
    async def _on_connected(transport_ref, ws):
        logger.info("Gemini Live client connected — pushing initial context")
        messages = [{"role": "system", "content": system_prompt}]
        if welcome_message:
            messages.append(
                {"role": "user", "content": welcome_message}
            )
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


async def _build_stt(provider: str, language: str):
    """Instantiate the correct STT service based on the agent config."""
    provider = provider.lower()

    if provider == "deepgram":
        from pipecat.services.deepgram.stt import DeepgramSTTService
        api_key = await _get_key("deepgram_api_key")
        return DeepgramSTTService(api_key=api_key)

    if provider in ("whisper", "openai"):
        from pipecat.services.openai.stt import OpenAISTTService
        api_key = await _get_key("openai_api_key")
        return OpenAISTTService(api_key=api_key, language=language)

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
            settings=OpenAISTTSettings(model="whisper-large-v3"),
        )

    if provider == "azure":
        from pipecat.services.azure.stt import AzureSTTService
        return AzureSTTService()

    raise ValueError(f"Unsupported STT provider: {provider}")


async def _build_tts(provider: str, voice: Optional[str], language: str):
    """Instantiate the correct TTS service based on the agent config."""
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
        return OpenAITTSService(
            api_key=api_key,
            settings=OpenAITTSSettings(voice=voice or "alloy"),
        )

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
