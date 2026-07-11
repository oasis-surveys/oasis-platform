"""
Resolve whether a provider has the credentials required to run.
"""

from __future__ import annotations

from redis.exceptions import RedisError

from app.config import settings

_PROVIDER_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "openai": ("openai_api_key",),
    "deepgram": ("deepgram_api_key",),
    "elevenlabs": ("elevenlabs_api_key",),
    "cartesia": ("cartesia_api_key",),
    "google": ("google_api_key",),
    "anthropic": ("anthropic_api_key",),
    "scaleway": ("scaleway_secret_key",),
    "azure": ("azure_openai_api_key", "azure_openai_endpoint", "azure_openai_api_version"),
    "gcp": ("gcp_project_id",),
    "custom": ("openai_compatible_llm_url",),
    "self_hosted_stt": ("self_hosted_stt_url",),
    "self_hosted_tts": ("self_hosted_tts_url",),
}

_DISABLED_PROVIDERS = frozenset({"azure", "gcp", "self_hosted_stt", "self_hosted_tts"})

async def is_provider_configured_async(provider: str) -> bool:
    """Check using dashboard Redis overrides when available."""
    if provider in _DISABLED_PROVIDERS:
        return False
    required = _PROVIDER_REQUIREMENTS.get(provider)
    if not required:
        return False
    from app.api.settings import get_effective_key

    try:
        for field in required:
            if not (await get_effective_key(field)).strip():
                return False
        return True
    except RedisError:
        return all(str(getattr(settings, field, "") or "").strip() for field in required)
