"""
Curated provider/model catalog for OASIS.

Single source of truth for dashboard options, API validation, and runtime routing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.providers.availability import (
    get_effective_provider_setting,
    is_provider_configured_async,
)

ApiKind = Literal[
    "chat_completions",
    "responses",
    "realtime",
    "gemini_live",
    "transcription_http",
    "transcription_realtime",
    "tts_http",
]

PipelineKind = Literal["modular", "voice_to_voice", "text"]


@dataclass(frozen=True)
class ModelOption:
    value: str
    label: str
    group: str
    provider: str
    api_kind: ApiKind
    pipelines: tuple[PipelineKind, ...]


@dataclass(frozen=True)
class ProviderOption:
    value: str
    label: str
    provider: str
    models: tuple[str, ...] | None = None  # None = free-form / env default


@dataclass(frozen=True)
class VoiceOption:
    value: str
    label: str
    provider: str


# ── LLM modular / text models ─────────────────────────────────────────────

LLM_MODULAR_MODELS: tuple[ModelOption, ...] = (
    # OpenAI
    ModelOption("openai/gpt-5.6-sol", "GPT-5.6 Sol (flagship)", "OpenAI", "openai", "responses", ("modular", "text")),
    ModelOption("openai/gpt-5.6-terra", "GPT-5.6 Terra (balanced)", "OpenAI", "openai", "responses", ("modular", "text")),
    ModelOption("openai/gpt-5.6-luna", "GPT-5.6 Luna (cost-efficient)", "OpenAI", "openai", "responses", ("modular", "text")),
    ModelOption("openai/gpt-5.5", "GPT-5.5", "OpenAI", "openai", "chat_completions", ("modular", "text")),
    ModelOption("openai/gpt-5.5-pro", "GPT-5.5 Pro", "OpenAI", "openai", "chat_completions", ("modular", "text")),
    ModelOption("openai/gpt-5.4", "GPT-5.4", "OpenAI", "openai", "chat_completions", ("modular", "text")),
    ModelOption("openai/gpt-5.4-pro", "GPT-5.4 Pro", "OpenAI", "openai", "chat_completions", ("modular", "text")),
    ModelOption("openai/gpt-5.4-mini", "GPT-5.4 Mini", "OpenAI", "openai", "chat_completions", ("modular", "text")),
    ModelOption("openai/gpt-5.4-nano", "GPT-5.4 Nano (cheapest)", "OpenAI", "openai", "chat_completions", ("modular", "text")),
    ModelOption("openai/gpt-5", "GPT-5", "OpenAI", "openai", "chat_completions", ("modular", "text")),
    ModelOption("openai/gpt-5-mini", "GPT-5 Mini", "OpenAI", "openai", "chat_completions", ("modular", "text")),
    ModelOption("openai/gpt-5-nano", "GPT-5 Nano", "OpenAI", "openai", "chat_completions", ("modular", "text")),
    ModelOption("openai/gpt-4.1", "GPT-4.1", "OpenAI", "openai", "chat_completions", ("modular", "text")),
    ModelOption("openai/gpt-4.1-mini", "GPT-4.1 Mini", "OpenAI", "openai", "chat_completions", ("modular", "text")),
    ModelOption("openai/gpt-4o", "GPT-4o", "OpenAI", "openai", "chat_completions", ("modular", "text")),
    ModelOption("openai/gpt-4o-mini", "GPT-4o Mini", "OpenAI", "openai", "chat_completions", ("modular", "text")),
    ModelOption("openai/o3", "o3 (reasoning)", "OpenAI", "openai", "chat_completions", ("modular", "text")),
    # Scaleway
    ModelOption("scaleway/qwen3.5-397b-a17b", "Qwen 3.5 397B A17B (newest)", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/mistral-medium-3.5-128b", "Mistral Medium 3.5 128B", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/qwen3-235b-a22b-instruct-2507", "Qwen 3 235B A22B Instruct", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/qwen3.6-35b-a3b", "Qwen 3.6 35B A3B (fast)", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/mistral-small-3.2-24b-instruct-2506", "Mistral Small 3.2 24B", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/voxtral-small-24b-2507", "Voxtral Small 24B (audio-capable)", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/gpt-oss-120b", "GPT-OSS 120B", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/llama-3.3-70b-instruct", "Llama 3.3 70B Instruct", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/gemma-4-26b-a4b-it", "Gemma 4 26B A4B IT", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/gemma-3-27b-it", "Gemma 3 27B IT", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/devstral-2-123b-instruct-2512", "Devstral 2 123B Instruct", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/pixtral-12b-2409", "Pixtral 12B (vision)", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    # Azure (requires full triple)
    ModelOption("azure/gpt-4o", "Azure GPT-4o", "Azure", "azure", "chat_completions", ("modular", "text")),
    ModelOption("azure/gpt-4o-mini", "Azure GPT-4o Mini", "Azure", "azure", "chat_completions", ("modular", "text")),
    # GCP Vertex
    ModelOption("gcp/gemini-2.5-flash", "GCP Gemini 2.5 Flash", "GCP (Vertex AI)", "gcp", "chat_completions", ("modular", "text")),
    ModelOption("gcp/gemini-2.5-pro", "GCP Gemini 2.5 Pro", "GCP (Vertex AI)", "gcp", "chat_completions", ("modular", "text")),
    ModelOption("gcp/gemini-2.0-flash", "GCP Gemini 2.0 Flash", "GCP (Vertex AI)", "gcp", "chat_completions", ("modular", "text")),
    # Anthropic
    ModelOption("anthropic/claude-opus-4-7", "Claude Opus 4.7 (most capable)", "Anthropic", "anthropic", "chat_completions", ("modular", "text")),
    ModelOption("anthropic/claude-sonnet-4-6", "Claude Sonnet 4.6 (balanced)", "Anthropic", "anthropic", "chat_completions", ("modular", "text")),
    ModelOption("anthropic/claude-haiku-4-5", "Claude Haiku 4.5 (fast)", "Anthropic", "anthropic", "chat_completions", ("modular", "text")),
    ModelOption("anthropic/claude-opus-4-6", "Claude Opus 4.6 (legacy)", "Anthropic", "anthropic", "chat_completions", ("modular", "text")),
    ModelOption("anthropic/claude-sonnet-4-5", "Claude Sonnet 4.5 (legacy)", "Anthropic", "anthropic", "chat_completions", ("modular", "text")),
    ModelOption("anthropic/claude-opus-4-5", "Claude Opus 4.5 (legacy)", "Anthropic", "anthropic", "chat_completions", ("modular", "text")),
    # Google AI
    ModelOption("google/gemini-3.5-flash", "Gemini 3.5 Flash (newest stable)", "Google AI", "google", "chat_completions", ("modular", "text")),
    ModelOption("google/gemini-3.1-pro-preview", "Gemini 3.1 Pro (preview)", "Google AI", "google", "chat_completions", ("modular", "text")),
    ModelOption("google/gemini-3-flash-preview", "Gemini 3 Flash (preview)", "Google AI", "google", "chat_completions", ("modular", "text")),
    ModelOption("google/gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite", "Google AI", "google", "chat_completions", ("modular", "text")),
    ModelOption("google/gemini-2.5-pro", "Gemini 2.5 Pro (stable)", "Google AI", "google", "chat_completions", ("modular", "text")),
)

LLM_V2V_MODELS: tuple[ModelOption, ...] = (
    ModelOption("openai/gpt-realtime-2.1", "GPT Realtime 2.1 (newest)", "OpenAI", "openai", "realtime", ("voice_to_voice",)),
    ModelOption("openai/gpt-realtime-2.1-mini", "GPT Realtime 2.1 Mini (cost-efficient)", "OpenAI", "openai", "realtime", ("voice_to_voice",)),
    ModelOption("openai/gpt-realtime-2", "GPT Realtime 2", "OpenAI", "openai", "realtime", ("voice_to_voice",)),
    ModelOption("openai/gpt-realtime-1.5", "GPT Realtime 1.5", "OpenAI", "openai", "realtime", ("voice_to_voice",)),
    ModelOption("openai/gpt-realtime", "GPT Realtime", "OpenAI", "openai", "realtime", ("voice_to_voice",)),
    ModelOption("openai/gpt-realtime-mini", "GPT Realtime Mini (cost-efficient)", "OpenAI", "openai", "realtime", ("voice_to_voice",)),
    ModelOption("google/gemini-3.1-flash-live-preview", "Gemini 3.1 Flash Live (newest preview)", "Google", "google", "gemini_live", ("voice_to_voice",)),
    ModelOption("google/gemini-2.5-flash-native-audio-latest", "Gemini 2.5 Flash Native Audio (latest)", "Google", "google", "gemini_live", ("voice_to_voice",)),
)

STT_PROVIDERS: tuple[ProviderOption, ...] = (
    ProviderOption("openai", "OpenAI Whisper", "openai", (
        "gpt-realtime-whisper", "whisper-1", "gpt-4o-transcribe",
        "gpt-4o-mini-transcribe", "gpt-4o-transcribe-diarize",
    )),
    ProviderOption("deepgram", "Deepgram", "deepgram", (
        "nova-3", "nova-3-medical", "nova-2", "nova-2-general",
        "nova-2-meeting", "nova-2-phonecall", "enhanced",
    )),
    ProviderOption("scaleway", "Scaleway Whisper", "scaleway", ("whisper-large-v3",)),
    ProviderOption(
        "self_hosted",
        "Custom / Self-Hosted",
        "self_hosted_stt",
        None,
    ),
)

TTS_PROVIDERS: tuple[ProviderOption, ...] = (
    ProviderOption("openai", "OpenAI TTS", "openai", ("gpt-4o-mini-tts", "tts-1", "tts-1-hd")),
    ProviderOption("elevenlabs", "ElevenLabs", "elevenlabs", None),
    ProviderOption("cartesia", "Cartesia (Sonic)", "cartesia", None),
    ProviderOption(
        "self_hosted",
        "Custom / Self-Hosted",
        "self_hosted_tts",
        None,
    ),
)

OPENAI_REALTIME_VOICES: tuple[VoiceOption, ...] = (
    VoiceOption("coral", "Coral (default)", "openai"),
    VoiceOption("alloy", "Alloy", "openai"),
    VoiceOption("ash", "Ash", "openai"),
    VoiceOption("ballad", "Ballad", "openai"),
    VoiceOption("echo", "Echo", "openai"),
    VoiceOption("fable", "Fable", "openai"),
    VoiceOption("onyx", "Onyx", "openai"),
    VoiceOption("nova", "Nova", "openai"),
    VoiceOption("sage", "Sage", "openai"),
    VoiceOption("shimmer", "Shimmer", "openai"),
    VoiceOption("verse", "Verse", "openai"),
)

GEMINI_LIVE_VOICES: tuple[VoiceOption, ...] = (
    VoiceOption("Charon", "Charon (default)", "google"),
    VoiceOption("Kore", "Kore", "google"),
    VoiceOption("Puck", "Puck", "google"),
    VoiceOption("Aoede", "Aoede", "google"),
    VoiceOption("Fenrir", "Fenrir", "google"),
    VoiceOption("Leda", "Leda", "google"),
    VoiceOption("Orus", "Orus", "google"),
    VoiceOption("Zephyr", "Zephyr", "google"),
)

OPENAI_TTS_VOICES: tuple[VoiceOption, ...] = (
    VoiceOption("alloy", "Alloy (Neutral)", "openai"),
    VoiceOption("echo", "Echo (Male)", "openai"),
    VoiceOption("fable", "Fable (Male)", "openai"),
    VoiceOption("onyx", "Onyx (Male)", "openai"),
    VoiceOption("nova", "Nova (Female)", "openai"),
    VoiceOption("shimmer", "Shimmer (Female)", "openai"),
)

ELEVENLABS_VOICES: tuple[VoiceOption, ...] = (
    VoiceOption("rachel", "Rachel (Female)", "elevenlabs"),
    VoiceOption("alice", "Alice (Female)", "elevenlabs"),
    VoiceOption("lily", "Lily (Female)", "elevenlabs"),
    VoiceOption("emily", "Emily (Female)", "elevenlabs"),
    VoiceOption("bella", "Bella (Female)", "elevenlabs"),
    VoiceOption("elli", "Elli (Female)", "elevenlabs"),
    VoiceOption("josh", "Josh (Male)", "elevenlabs"),
    VoiceOption("adam", "Adam (Male)", "elevenlabs"),
    VoiceOption("arnold", "Arnold (Male)", "elevenlabs"),
    VoiceOption("sam", "Sam (Male)", "elevenlabs"),
    VoiceOption("charlie", "Charlie (Male)", "elevenlabs"),
    VoiceOption("bill", "Bill (Male)", "elevenlabs"),
    VoiceOption("george", "George (Male)", "elevenlabs"),
)

CARTESIA_VOICES: tuple[VoiceOption, ...] = (
    VoiceOption("a0e99841-438c-4a64-b679-ae501e7d6091", "Barbershop Man (default)", "cartesia"),
    VoiceOption("729651dc-c6c3-4ee5-97fa-350da1f88600", "Storyteller (Female)", "cartesia"),
    VoiceOption("5345cf08-6f37-424d-a5d9-8ae1101b9377", "British Reading Lady", "cartesia"),
    VoiceOption("421b3369-f63f-4b03-8980-37a44df1d4e8", "Friendly Brit", "cartesia"),
    VoiceOption("00a77add-48d5-4ef6-8157-71e5437b282d", "Calm Lady", "cartesia"),
)

STT_MODEL_LABELS: dict[str, str] = {
    "gpt-realtime-whisper": "GPT Realtime Whisper (streaming)",
    "whisper-1": "Whisper 1",
    "gpt-4o-transcribe": "GPT-4o Transcribe",
    "gpt-4o-mini-transcribe": "GPT-4o Mini Transcribe",
    "gpt-4o-transcribe-diarize": "GPT-4o Transcribe Diarize (multi-speaker)",
    "whisper-large-v3": "Whisper Large V3",
    "nova-3": "Nova 3 (default)",
    "nova-3-medical": "Nova 3 Medical",
    "nova-2": "Nova 2",
    "nova-2-general": "Nova 2 General",
    "nova-2-meeting": "Nova 2 Meeting",
    "nova-2-phonecall": "Nova 2 Phone Call",
    "enhanced": "Enhanced",
}

TTS_MODEL_LABELS: dict[str, str] = {
    "gpt-4o-mini-tts": "GPT-4o Mini TTS (default)",
    "tts-1": "TTS-1 (fast)",
    "tts-1-hd": "TTS-1 HD (quality)",
}

DEFAULTS = {
    "modular_llm": "openai/gpt-5.6-luna",
    "text_llm": "openai/gpt-5.6-luna",
    "v2v_llm": "openai/gpt-realtime-2.1-mini",
    "stt_provider": "openai",
    "stt_model": "gpt-realtime-whisper",
    "tts_provider": "openai",
    "tts_model": "gpt-4o-mini-tts",
    "tts_voice": "alloy",
    "v2v_voice_openai": "coral",
    "v2v_voice_google": "Charon",
    "self_hosted_stt_model": "whisper-1",
    "self_hosted_tts_model": "tts-1",
    "self_hosted_tts_voice": "alloy",
}

_LLM_BY_VALUE: dict[str, ModelOption] = {
    m.value: m for m in (*LLM_MODULAR_MODELS, *LLM_V2V_MODELS)
}


def _llm_prefix(model: str) -> str:
    if model.startswith("custom/"):
        return "custom"
    if "/" in model:
        return model.split("/", 1)[0]
    return "openai"


def get_catalog_entry(model: str) -> ModelOption | None:
    return _LLM_BY_VALUE.get(model)


def resolve_llm_api_kind(model: str) -> ApiKind | None:
    entry = get_catalog_entry(model)
    if entry:
        return entry.api_kind
    prefix = _llm_prefix(model)
    if prefix == "openai":
        if "gpt-5.6" in model:
            return "responses"
        if "realtime" in model.lower():
            return "realtime"
        return "chat_completions"
    if prefix == "google" and ("live" in model.lower() or "native-audio" in model.lower()):
        return "gemini_live"
    if prefix in ("anthropic", "scaleway", "azure", "gcp", "custom"):
        return "chat_completions"
    return None


def list_all_llm_models() -> tuple[ModelOption, ...]:
    return (*LLM_MODULAR_MODELS, *LLM_V2V_MODELS)


def list_v2v_models() -> tuple[ModelOption, ...]:
    return LLM_V2V_MODELS


def list_stt_models(provider: str) -> list[dict]:
    for p in STT_PROVIDERS:
        if p.value == provider and p.models:
            return [
                {"value": m, "label": STT_MODEL_LABELS.get(m, m)}
                for m in p.models
            ]
    return []


def list_tts_models(provider: str) -> list[dict]:
    for p in TTS_PROVIDERS:
        if p.value == provider and p.models:
            return [
                {"value": m, "label": TTS_MODEL_LABELS.get(m, m)}
                for m in p.models
            ]
    return []


def list_v2v_voices(llm_model: str) -> list[dict]:
    if llm_model.startswith("google/"):
        return [{"value": v.value, "label": v.label} for v in GEMINI_LIVE_VOICES]
    return [{"value": v.value, "label": v.label} for v in OPENAI_REALTIME_VOICES]


async def _filter_models(models: tuple[ModelOption, ...], pipeline: PipelineKind | None = None) -> list[dict]:
    out = []
    for m in models:
        if pipeline and pipeline not in m.pipelines:
            continue
        if not await is_provider_configured_async(m.provider):
            continue
        out.append({
            "value": m.value,
            "label": m.label,
            "group": m.group,
            "provider": m.provider,
            "api_kind": m.api_kind,
        })
    return out


async def get_configured_catalog() -> dict:
    """Return only providers/models whose credentials are fully configured."""
    modular = await _filter_models(LLM_MODULAR_MODELS, "modular")
    text = await _filter_models(LLM_MODULAR_MODELS, "text")
    v2v = await _filter_models(LLM_V2V_MODELS, "voice_to_voice")

    stt_providers = []
    for p in STT_PROVIDERS:
        if await is_provider_configured_async(p.provider):
            models = list_stt_models(p.value)
            if p.value == "self_hosted":
                model = (
                    await get_effective_provider_setting("self_hosted_stt_model")
                    or DEFAULTS["self_hosted_stt_model"]
                )
                models = [{
                    "value": model,
                    "label": model,
                }]
            stt_providers.append({
                "value": p.value,
                "label": p.label,
                "provider": p.provider,
                "models": models,
            })

    tts_providers = []
    for p in TTS_PROVIDERS:
        if await is_provider_configured_async(p.provider):
            models = list_tts_models(p.value)
            if p.value == "self_hosted":
                model = (
                    await get_effective_provider_setting("self_hosted_tts_model")
                    or DEFAULTS["self_hosted_tts_model"]
                )
                models = [{
                    "value": model,
                    "label": model,
                }]
            tts_providers.append({
                "value": p.value,
                "label": p.label,
                "provider": p.provider,
                "models": models,
            })

    voices = {
        "openai_realtime": [{"value": v.value, "label": v.label} for v in OPENAI_REALTIME_VOICES],
        "gemini_live": [{"value": v.value, "label": v.label} for v in GEMINI_LIVE_VOICES],
        "openai_tts": [{"value": v.value, "label": v.label} for v in OPENAI_TTS_VOICES],
        "elevenlabs": [{"value": v.value, "label": v.label} for v in ELEVENLABS_VOICES],
        "cartesia": [{"value": v.value, "label": v.label} for v in CARTESIA_VOICES],
    }

    if not await is_provider_configured_async("openai"):
        voices["openai_realtime"] = []
        voices["openai_tts"] = []
    if not await is_provider_configured_async("google"):
        voices["gemini_live"] = []
    if not await is_provider_configured_async("elevenlabs"):
        voices["elevenlabs"] = []
    if not await is_provider_configured_async("cartesia"):
        voices["cartesia"] = []

    return {
        "defaults": DEFAULTS,
        "llm_modular": modular,
        "llm_text": text,
        "llm_v2v": v2v,
        "stt_providers": stt_providers,
        "tts_providers": tts_providers,
        "voices": voices,
        "supports_custom_llm": await is_provider_configured_async("custom"),
    }
