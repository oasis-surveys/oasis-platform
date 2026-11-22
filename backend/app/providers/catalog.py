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
    ModelOption("openai/gpt-6.2-astra", "GPT-6.2 Astra (most capable)", "OpenAI", "openai", "responses", ("modular", "text")),
    ModelOption("openai/gpt-6.2-sol", "GPT-6.2 Sol", "OpenAI", "openai", "responses", ("modular", "text")),
    ModelOption("openai/gpt-6.1-terra", "GPT-6.1 Terra", "OpenAI", "openai", "responses", ("modular", "text")),
    ModelOption("openai/gpt-6-luna", "GPT-6 Luna (cost-efficient)", "OpenAI", "openai", "responses", ("modular", "text")),
    ModelOption("openai/gpt-5.6-sol", "GPT-5.6 Sol", "OpenAI", "openai", "responses", ("modular", "text")),
    ModelOption("openai/gpt-5.6-terra", "GPT-5.6 Terra", "OpenAI", "openai", "responses", ("modular", "text")),
    ModelOption("openai/gpt-5.6-luna", "GPT-5.6 Luna (default)", "OpenAI", "openai", "responses", ("modular", "text")),
    ModelOption("openai/gpt-5.5", "GPT-5.5", "OpenAI", "openai", "chat_completions", ("modular", "text")),
    ModelOption("openai/gpt-5.5-pro", "GPT-5.5 Pro (slow)", "OpenAI", "openai", "responses", ("modular", "text")),
    ModelOption("openai/gpt-5.4", "GPT-5.4", "OpenAI", "openai", "chat_completions", ("modular", "text")),
    ModelOption("openai/gpt-5.4-pro", "GPT-5.4 Pro (slow)", "OpenAI", "openai", "responses", ("modular", "text")),
    ModelOption("openai/gpt-5.4-mini", "GPT-5.4 Mini", "OpenAI", "openai", "chat_completions", ("modular", "text")),
    ModelOption("openai/gpt-5.4-nano", "GPT-5.4 Nano (shuts down Apr 1, 2027)", "OpenAI", "openai", "chat_completions", ("modular", "text")),
    # Scaleway
    ModelOption("scaleway/qwen3.8-27b", "Qwen 3.8 27B (newest)", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/qwen3.6-35b-a3b", "Qwen 3.6 35B A3B (fast)", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/qwen3.5-397b-a17b", "Qwen 3.5 397B A17B", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/qwen3-235b-a22b-instruct-2507", "Qwen 3 235B A22B Instruct", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/deepseek-v4.1-flash-1017", "DeepSeek V4.1 Flash", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/glm-5.3", "GLM 5.3", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/mistral-medium-3.5-128b", "Mistral Medium 3.5 128B", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/mistral-small-3.2-24b-instruct-2506", "Mistral Small 3.2 24B", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/gpt-oss-120b", "GPT-OSS 120B", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/llama-3.3-70b-instruct", "Llama 3.3 70B Instruct", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    ModelOption("scaleway/gemma-4-26b-a4b-it", "Gemma 4 26B A4B IT", "Scaleway", "scaleway", "chat_completions", ("modular", "text")),
    # Azure chat deployments are added from AZURE_OPENAI_CHAT_DEPLOYMENTS.
    # GCP Vertex
    ModelOption("gcp/gemini-3.8-flash", "GCP Gemini 3.8 Flash", "GCP (Vertex AI)", "gcp", "chat_completions", ("modular", "text")),
    ModelOption("gcp/gemini-3.5-flash", "GCP Gemini 3.5 Flash", "GCP (Vertex AI)", "gcp", "chat_completions", ("modular", "text")),
    ModelOption("gcp/gemini-2.5-flash", "GCP Gemini 2.5 Flash", "GCP (Vertex AI)", "gcp", "chat_completions", ("modular", "text")),
    ModelOption("gcp/gemini-2.5-pro", "GCP Gemini 2.5 Pro", "GCP (Vertex AI)", "gcp", "chat_completions", ("modular", "text")),
    # Anthropic
    ModelOption("anthropic/claude-fable-5-2", "Claude Fable 5.2 (most capable)", "Anthropic", "anthropic", "chat_completions", ("modular", "text")),
    ModelOption("anthropic/claude-opus-5-5", "Claude Opus 5.5 (recommended)", "Anthropic", "anthropic", "chat_completions", ("modular", "text")),
    ModelOption("anthropic/claude-sonnet-5-5", "Claude Sonnet 5.5 (balanced)", "Anthropic", "anthropic", "chat_completions", ("modular", "text")),
    ModelOption("anthropic/claude-haiku-5-5", "Claude Haiku 5.5 (fast)", "Anthropic", "anthropic", "chat_completions", ("modular", "text")),
    ModelOption("anthropic/claude-opus-4-8", "Claude Opus 4.8 (legacy)", "Anthropic", "anthropic", "chat_completions", ("modular", "text")),
    ModelOption("anthropic/claude-opus-4-7", "Claude Opus 4.7 (legacy)", "Anthropic", "anthropic", "chat_completions", ("modular", "text")),
    ModelOption("anthropic/claude-sonnet-4-6", "Claude Sonnet 4.6 (legacy)", "Anthropic", "anthropic", "chat_completions", ("modular", "text")),
    ModelOption("anthropic/claude-haiku-4-5", "Claude Haiku 4.5 (legacy)", "Anthropic", "anthropic", "chat_completions", ("modular", "text")),
    # Google AI
    ModelOption("google/gemini-3.8-flash", "Gemini 3.8 Flash (newest Flash)", "Google AI", "google", "chat_completions", ("modular", "text")),
    ModelOption("google/gemini-3.5-flash", "Gemini 3.5 Flash", "Google AI", "google", "chat_completions", ("modular", "text")),
    ModelOption("google/gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite (fastest)", "Google AI", "google", "chat_completions", ("modular", "text")),
    ModelOption("google/gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite", "Google AI", "google", "chat_completions", ("modular", "text")),
    ModelOption("google/gemini-4-hydrogen", "Gemini 4 Hydrogen (slow for voice)", "Google AI", "google", "chat_completions", ("modular", "text")),
    ModelOption("google/gemini-4-neon", "Gemini 4 Neon (paid tier, slow for voice)", "Google AI", "google", "chat_completions", ("modular", "text")),
    ModelOption("google/gemini-4-carbon", "Gemini 4 Carbon (paid tier, slow for voice)", "Google AI", "google", "chat_completions", ("modular", "text")),
    ModelOption("google/gemini-3.1-pro-preview", "Gemini 3.1 Pro (preview, paid tier)", "Google AI", "google", "chat_completions", ("modular", "text")),
)

LLM_V2V_MODELS: tuple[ModelOption, ...] = (
    ModelOption("openai/gpt-realtime-2.1", "GPT Realtime 2.1 (newest)", "OpenAI", "openai", "realtime", ("voice_to_voice",)),
    ModelOption("openai/gpt-realtime-2.1-mini", "GPT Realtime 2.1 Mini (cost-efficient)", "OpenAI", "openai", "realtime", ("voice_to_voice",)),
    ModelOption("openai/gpt-realtime-2", "GPT Realtime 2", "OpenAI", "openai", "realtime", ("voice_to_voice",)),
    ModelOption("openai/gpt-realtime-1.5", "GPT Realtime 1.5", "OpenAI", "openai", "realtime", ("voice_to_voice",)),
    ModelOption("openai/gpt-realtime", "GPT Realtime (shuts down Jan 20, 2027)", "OpenAI", "openai", "realtime", ("voice_to_voice",)),
    ModelOption("openai/gpt-realtime-mini", "GPT Realtime Mini (shuts down Jan 20, 2027)", "OpenAI", "openai", "realtime", ("voice_to_voice",)),
    ModelOption("google/gemini-3.8-live", "Gemini 3.8 Live (newest)", "Google", "google", "gemini_live", ("voice_to_voice",)),
    ModelOption("google/gemini-3.1-flash-live-preview", "Gemini 3.1 Flash Live (preview)", "Google", "google", "gemini_live", ("voice_to_voice",)),
    ModelOption("google/gemini-2.5-flash-native-audio-latest", "Gemini 2.5 Flash Native Audio (latest)", "Google", "google", "gemini_live", ("voice_to_voice",)),
)

STT_PROVIDERS: tuple[ProviderOption, ...] = (
    ProviderOption("openai", "OpenAI Whisper", "openai", (
        "gpt-realtime-whisper", "gpt-live-transcribe", "gpt-transcribe",
        "whisper-1", "gpt-4o-transcribe", "gpt-4o-mini-transcribe",
        "gpt-4o-transcribe-diarize",
    )),
    ProviderOption("deepgram", "Deepgram", "deepgram", (
        "nova-3", "nova-3-medical", "nova-2", "nova-2-general",
        "nova-2-meeting", "nova-2-phonecall", "enhanced",
    )),
    ProviderOption("scaleway", "Scaleway Whisper", "scaleway", ("whisper-large-v3",)),
    ProviderOption("azure_openai", "Azure OpenAI", "azure_openai_stt", None),
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
    ProviderOption("azure_openai", "Azure OpenAI", "azure_openai_tts", None),
    ProviderOption(
        "self_hosted",
        "Custom / Self-Hosted",
        "self_hosted_tts",
        None,
    ),
)

OPENAI_REALTIME_VOICES: tuple[VoiceOption, ...] = (
    VoiceOption("coral", "Coral (default)", "openai"),
    VoiceOption("marin", "Marin (best quality)", "openai"),
    VoiceOption("cedar", "Cedar (best quality)", "openai"),
    VoiceOption("alloy", "Alloy", "openai"),
    VoiceOption("ash", "Ash", "openai"),
    VoiceOption("ballad", "Ballad", "openai"),
    VoiceOption("echo", "Echo", "openai"),
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
    VoiceOption("talia", "Talia (warm, soft)", "elevenlabs"),
    VoiceOption("alicia", "Alicia (polished)", "elevenlabs"),
    VoiceOption("jade", "Jade (upbeat, natural)", "elevenlabs"),
    VoiceOption("elara", "Elara (crisp)", "elevenlabs"),
    VoiceOption("maisie", "Maisie (friendly, casual)", "elevenlabs"),
    VoiceOption("elowen", "Elowen (upbeat)", "elevenlabs"),
    VoiceOption("florence", "Florence (atmospheric)", "elevenlabs"),
    VoiceOption("eddie", "Eddie (natural, helpful)", "elevenlabs"),
    VoiceOption("caleb", "Caleb (trusted guide)", "elevenlabs"),
    VoiceOption("finley", "Finley (articulate)", "elevenlabs"),
    VoiceOption("lawrence", "Lawrence (bright)", "elevenlabs"),
    VoiceOption("wyatt", "Wyatt (seasoned)", "elevenlabs"),
    VoiceOption("eldrin", "Eldrin (British baritone)", "elevenlabs"),
    VoiceOption("darian", "Darian (warm, grounded)", "elevenlabs"),
    VoiceOption("warren", "Warren (cool, easy)", "elevenlabs"),
    VoiceOption("baxter", "Baxter (calm, Australian)", "elevenlabs"),
)

# ElevenLabs retires its Default voices on Dec 31, 2026. Agents saved with an
# old name keep working through the replacement ElevenLabs suggests, or a
# similar voice where it suggests none.
ELEVENLABS_RETIRED_VOICES: dict[str, str] = {
    "rachel": "talia",
    "sarah": "talia",
    "bella": "talia",
    "domi": "jade",
    "elli": "maisie",
    "emily": "elara",
    "alice": "alicia",
    "lily": "florence",
    "charlie": "baxter",
    "chris": "caleb",
    "bill": "wyatt",
    "george": "eldrin",
    "antoni": "eddie",
    "josh": "lawrence",
    "arnold": "eldrin",
    "adam": "finley",
    "sam": "eddie",
}

CARTESIA_VOICES: tuple[VoiceOption, ...] = (
    VoiceOption("db6b0ed5-d5d3-463d-ae85-518a07d3c2b4", "Skylar (US, female)", "cartesia"),
    VoiceOption("47c38ca4-5f35-497b-b1a3-415245fb35e1", "Daniel (US, male)", "cartesia"),
    VoiceOption("9626c31c-bec5-4cca-baa8-f8ba9e84c8bc", "Jacqueline (US, female)", "cartesia"),
    VoiceOption("62ae83ad-4f6a-430b-af41-a9bede9286ca", "Gemma (UK, female)", "cartesia"),
    VoiceOption("ef191366-f52f-447a-a398-ed8c0f2943a1", "Archie (UK, male)", "cartesia"),
    VoiceOption("a0e99841-438c-4a64-b679-ae501e7d6091", "Barbershop Man", "cartesia"),
    VoiceOption("729651dc-c6c3-4ee5-97fa-350da1f88600", "Storyteller (Female)", "cartesia"),
    VoiceOption("5345cf08-6f37-424d-a5d9-8ae1101b9377", "British Reading Lady", "cartesia"),
    VoiceOption("421b3369-f63f-4b03-8980-37a44df1d4e8", "Friendly Brit", "cartesia"),
    VoiceOption("00a77add-48d5-4ef6-8157-71e5437b282d", "Calm Lady", "cartesia"),
)

STT_MODEL_LABELS: dict[str, str] = {
    "gpt-realtime-whisper": "GPT Realtime Whisper (streaming)",
    "gpt-live-transcribe": "GPT Live Transcribe (streaming)",
    "gpt-transcribe": "GPT Transcribe",
    "whisper-1": "Whisper 1 (shuts down Feb 26, 2027)",
    "gpt-4o-transcribe": "GPT-4o Transcribe (shuts down Feb 26, 2027)",
    "gpt-4o-mini-transcribe": "GPT-4o Mini Transcribe (shuts down Feb 26, 2027)",
    "gpt-4o-transcribe-diarize": "GPT-4o Transcribe Diarize (shuts down Feb 26, 2027)",
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
    "gpt-4o-mini-tts": "GPT-4o Mini TTS (shuts down Jan 6, 2027)",
    "tts-1": "TTS-1 (shuts down Jan 6, 2027)",
    "tts-1-hd": "TTS-1 HD (shuts down Jan 6, 2027)",
}

DEFAULTS = {
    "modular_llm": "openai/gpt-5.6-luna",
    "text_llm": "openai/gpt-5.6-luna",
    "v2v_llm": "openai/gpt-realtime-2.1-mini",
    "stt_provider": "openai",
    "stt_model": "gpt-realtime-whisper",
    "tts_provider": "elevenlabs",
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


def deployment_names(raw: str) -> list[str]:
    """Split a comma-separated Azure deployment list."""
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


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
        if "gpt-5.6" in model or "gpt-6" in model:
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


async def _azure_setting(field: str) -> str:
    return await get_effective_provider_setting(field)


async def get_configured_catalog() -> dict:
    """Return only providers/models whose credentials are fully configured."""
    modular = await _filter_models(LLM_MODULAR_MODELS, "modular")
    text = await _filter_models(LLM_MODULAR_MODELS, "text")
    v2v = await _filter_models(LLM_V2V_MODELS, "voice_to_voice")

    if await is_provider_configured_async("azure"):
        for name in deployment_names(await _azure_setting("azure_openai_chat_deployments")):
            option = {
                "value": f"azure/{name}",
                "label": name,
                "group": "Azure OpenAI",
                "provider": "azure",
                "api_kind": "chat_completions",
            }
            modular.append(option)
            text.append(option)

    if await is_provider_configured_async("azure_openai_realtime"):
        name = await _azure_setting("azure_openai_realtime_deployment")
        v2v.append({
            "value": f"azure/{name}",
            "label": name,
            "group": "Azure OpenAI",
            "provider": "azure",
            "api_kind": "realtime",
        })

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
            elif p.value == "azure_openai":
                model = await _azure_setting("azure_openai_stt_deployment")
                models = [{"value": model, "label": model}]
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
            elif p.value == "azure_openai":
                model = await _azure_setting("azure_openai_tts_deployment")
                models = [{"value": model, "label": model}]
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

    if not (
        await is_provider_configured_async("openai")
        or await is_provider_configured_async("azure_openai_realtime")
    ):
        voices["openai_realtime"] = []
    if not (
        await is_provider_configured_async("openai")
        or await is_provider_configured_async("azure_openai_tts")
    ):
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
        "supports_custom_llm": (
            await is_provider_configured_async("custom")
            or await is_provider_configured_async("azure")
        ),
    }
