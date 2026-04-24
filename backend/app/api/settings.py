"""
OASIS — Settings API endpoints.

GET  /api/settings/keys       — List configured API keys (masked)
PUT  /api/settings/keys       — Update API key overrides (stored in Redis)
GET  /api/settings/auth       — Get auth configuration status
"""

import re
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

from app.config import settings
from app.redis import get_redis

router = APIRouter(prefix="/settings", tags=["Settings"])

# Redis key for API key overrides
_REDIS_KEY = "oasis:settings:api_keys"

# All configurable API keys with their .env variable names
_API_KEY_FIELDS = {
    "openai_api_key": "OPENAI_API_KEY",
    "deepgram_api_key": "DEEPGRAM_API_KEY",
    "elevenlabs_api_key": "ELEVENLABS_API_KEY",
    "cartesia_api_key": "CARTESIA_API_KEY",
    "google_api_key": "GOOGLE_API_KEY",
    "scaleway_secret_key": "SCALEWAY_SECRET_KEY",
    "azure_openai_api_key": "AZURE_OPENAI_API_KEY",
    "azure_openai_endpoint": "AZURE_OPENAI_ENDPOINT",
    "gcp_project_id": "GCP_PROJECT_ID",
    "gcp_api_key": "GCP_API_KEY",
    "self_hosted_stt_url": "SELF_HOSTED_STT_URL",
    "self_hosted_stt_api_key": "SELF_HOSTED_STT_API_KEY",
    "self_hosted_stt_model": "SELF_HOSTED_STT_MODEL",
    "self_hosted_tts_url": "SELF_HOSTED_TTS_URL",
    "self_hosted_tts_api_key": "SELF_HOSTED_TTS_API_KEY",
    "self_hosted_tts_model": "SELF_HOSTED_TTS_MODEL",
    "embedding_api_url": "EMBEDDING_API_URL",
    "embedding_api_key": "EMBEDDING_API_KEY",
    "embedding_model": "EMBEDDING_MODEL",
    "twilio_account_sid": "TWILIO_ACCOUNT_SID",
    "twilio_auth_token": "TWILIO_AUTH_TOKEN",
    "twilio_phone_number": "TWILIO_PHONE_NUMBER",
}


def _mask_key(value: str) -> str:
    """Mask an API key for display, showing only last 4 chars."""
    if not value or len(value) < 8:
        return "••••" if value else ""
    return "••••••••" + value[-4:]


class ApiKeyStatus(BaseModel):
    field: str
    env_var: str
    is_set: bool
    source: str  # "env", "dashboard", or "none"
    masked_value: str


class ApiKeysResponse(BaseModel):
    keys: list[ApiKeyStatus]


class ApiKeyUpdate(BaseModel):
    """Update one or more API keys. Only provided fields are updated."""
    openai_api_key: Optional[str] = None
    deepgram_api_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None
    cartesia_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    scaleway_secret_key: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    gcp_project_id: Optional[str] = None
    gcp_api_key: Optional[str] = None
    self_hosted_stt_url: Optional[str] = None
    self_hosted_stt_api_key: Optional[str] = None
    self_hosted_stt_model: Optional[str] = None
    self_hosted_tts_url: Optional[str] = None
    self_hosted_tts_api_key: Optional[str] = None
    self_hosted_tts_model: Optional[str] = None
    embedding_api_url: Optional[str] = None
    embedding_api_key: Optional[str] = None
    embedding_model: Optional[str] = None
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None


class AuthConfigResponse(BaseModel):
    auth_enabled: bool
    username: str


async def get_effective_key(field: str) -> str:
    """
    Get the effective value for an API key field.
    Dashboard overrides (Redis) take priority over .env values.
    """
    redis = await get_redis()
    override = await redis.hget(_REDIS_KEY, field)
    if override:
        return override
    return getattr(settings, field, "")


async def _get_all_overrides() -> dict[str, str]:
    """Get all Redis-stored API key overrides."""
    redis = await get_redis()
    return await redis.hgetall(_REDIS_KEY)


@router.get("/keys", response_model=ApiKeysResponse)
async def list_api_keys():
    """List all configurable API keys with their status (masked)."""
    overrides = await _get_all_overrides()
    keys = []

    for field, env_var in _API_KEY_FIELDS.items():
        env_value = getattr(settings, field, "")
        override_value = overrides.get(field, "")

        if override_value:
            source = "dashboard"
            effective = override_value
        elif env_value:
            source = "env"
            effective = env_value
        else:
            source = "none"
            effective = ""

        keys.append(
            ApiKeyStatus(
                field=field,
                env_var=env_var,
                is_set=bool(effective),
                source=source,
                masked_value=_mask_key(effective),
            )
        )

    return ApiKeysResponse(keys=keys)


@router.put("/keys", response_model=ApiKeysResponse)
async def update_api_keys(data: ApiKeyUpdate):
    """
    Update API key overrides. These are stored in Redis and take
    priority over .env values. Send an empty string to clear an override.
    """
    redis = await get_redis()
    updates = data.model_dump(exclude_none=True)

    for field, value in updates.items():
        if field not in _API_KEY_FIELDS:
            continue

        if value == "":
            # Clear the override — fall back to .env
            await redis.hdel(_REDIS_KEY, field)
            logger.info(f"Cleared API key override: {field}")
        else:
            await redis.hset(_REDIS_KEY, field, value)
            logger.info(f"Set API key override: {field}")

    # Return updated status
    return await list_api_keys()


@router.get("/auth", response_model=AuthConfigResponse)
async def get_auth_config():
    """Get the current authentication configuration."""
    return AuthConfigResponse(
        auth_enabled=settings.auth_enabled,
        username=settings.auth_username,
    )
