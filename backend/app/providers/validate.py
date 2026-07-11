"""
Validate agent pipeline configuration against the provider catalog.
"""

from __future__ import annotations

from app.providers.availability import is_provider_configured_async
from app.providers.catalog import (
    CARTESIA_VOICES,
    ELEVENLABS_VOICES,
    GEMINI_LIVE_VOICES,
    OPENAI_REALTIME_VOICES,
    OPENAI_TTS_VOICES,
    STT_PROVIDERS,
    TTS_PROVIDERS,
    get_catalog_entry,
    list_stt_models,
    list_tts_models,
)


def _modality_value(modality) -> str:
    return modality.value if hasattr(modality, "value") else str(modality)


def _pipeline_value(pipeline_type) -> str:
    return pipeline_type.value if hasattr(pipeline_type, "value") else str(pipeline_type)


async def validate_agent_pipeline_config(
    *,
    modality,
    pipeline_type,
    llm_model: str,
    stt_provider: str | None = None,
    stt_model: str | None = None,
    tts_provider: str | None = None,
    tts_model: str | None = None,
    tts_voice: str | None = None,
) -> list[str]:
    """Return human-readable validation errors (empty if valid)."""
    errors: list[str] = []
    mod = _modality_value(modality)
    pipe = _pipeline_value(pipeline_type)

    if mod == "text" and pipe != "modular":
        errors.append("Text agents must use the modular pipeline.")

    entry = get_catalog_entry(llm_model)
    prefix = llm_model.split("/", 1)[0] if "/" in llm_model else "openai"

    if mod == "text":
        if entry and "text" not in entry.pipelines:
            errors.append(f"Model '{llm_model}' is not available for text chat.")
        elif not entry and prefix == "custom":
            if not await is_provider_configured_async("custom"):
                errors.append("Custom LLM requires OPENAI_COMPATIBLE_LLM_URL to be configured.")
        elif not entry and prefix not in ("openai", "anthropic", "google", "scaleway"):
            errors.append(f"Model '{llm_model}' is not in the supported catalog.")
        elif not entry and not await is_provider_configured_async(prefix):
            errors.append(f"Provider '{prefix}' is not configured.")
        elif entry and not await is_provider_configured_async(entry.provider):
            errors.append(f"Provider '{entry.provider}' is not configured for model '{llm_model}'.")

    elif pipe == "voice_to_voice":
        if not entry or "voice_to_voice" not in entry.pipelines:
            errors.append(
                f"Model '{llm_model}' is not a voice-to-voice model. "
                "Choose an OpenAI Realtime or Gemini Live model."
            )
        elif not await is_provider_configured_async(entry.provider):
            errors.append(f"Provider '{entry.provider}' is not configured for voice-to-voice.")
        if tts_voice and entry:
            if entry.provider == "google":
                allowed = {v.value for v in GEMINI_LIVE_VOICES}
            else:
                allowed = {v.value for v in OPENAI_REALTIME_VOICES}
            if tts_voice not in allowed:
                errors.append(f"Voice '{tts_voice}' is not valid for {llm_model}.")

    else:
        if entry and "modular" not in entry.pipelines:
            errors.append(
                f"Model '{llm_model}' cannot be used in the modular voice pipeline."
            )
        elif not entry and prefix == "custom":
            if not await is_provider_configured_async("custom"):
                errors.append("Custom LLM requires OPENAI_COMPATIBLE_LLM_URL to be configured.")
        elif not entry and prefix not in ("openai", "anthropic", "google", "scaleway"):
            errors.append(f"Model '{llm_model}' is not in the supported catalog.")
        elif not entry and not await is_provider_configured_async(prefix):
            errors.append(f"Provider '{prefix}' is not configured.")
        elif entry and not await is_provider_configured_async(entry.provider):
            errors.append(f"Provider '{entry.provider}' is not configured.")

        if stt_provider:
            stt_ok = any(p.value == stt_provider for p in STT_PROVIDERS)
            if not stt_ok:
                errors.append(f"STT provider '{stt_provider}' is not supported.")
            elif not await is_provider_configured_async(
                next(p.provider for p in STT_PROVIDERS if p.value == stt_provider)
            ):
                errors.append(f"STT provider '{stt_provider}' is not configured.")
            elif stt_model:
                allowed = {m["value"] for m in list_stt_models(stt_provider)}
                if allowed and stt_model not in allowed:
                    errors.append(f"STT model '{stt_model}' is not valid for {stt_provider}.")

        if tts_provider:
            tts_ok = any(p.value == tts_provider for p in TTS_PROVIDERS)
            if not tts_ok:
                errors.append(f"TTS provider '{tts_provider}' is not supported.")
            elif not await is_provider_configured_async(
                next(p.provider for p in TTS_PROVIDERS if p.value == tts_provider)
            ):
                errors.append(f"TTS provider '{tts_provider}' is not configured.")
            elif tts_model:
                allowed = {m["value"] for m in list_tts_models(tts_provider)}
                if allowed and tts_model not in allowed:
                    errors.append(f"TTS model '{tts_model}' is not valid for {tts_provider}.")
            if tts_voice:
                if tts_provider == "openai":
                    allowed = {v.value for v in OPENAI_TTS_VOICES}
                elif tts_provider == "elevenlabs":
                    allowed = {v.value for v in ELEVENLABS_VOICES}
                elif tts_provider == "cartesia":
                    allowed = {v.value for v in CARTESIA_VOICES}
                else:
                    allowed = None
                if allowed is not None and tts_voice not in allowed:
                    errors.append(f"TTS voice '{tts_voice}' is not valid for {tts_provider}.")

    return errors
