"""
Tests for the provider capability catalog, validation, and settings endpoints.
"""

import pytest
from httpx import AsyncClient

from app.providers.catalog import (
    DEFAULTS,
    LLM_MODULAR_MODELS,
    LLM_V2V_MODELS,
    get_catalog_entry,
    list_all_llm_models,
    resolve_llm_api_kind,
)
from app.providers.smoke import run_configured_smoke_tests
from app.providers.validate import validate_agent_pipeline_config


class TestProviderCatalog:
    def test_every_llm_has_catalog_entry(self):
        for model in list_all_llm_models():
            assert get_catalog_entry(model.value) is not None
            assert model.provider
            assert model.api_kind

    def test_gpt_56_uses_responses_api(self):
        assert resolve_llm_api_kind("openai/gpt-5.6-luna") == "responses"

    def test_gpt_4o_uses_chat_completions(self):
        assert resolve_llm_api_kind("openai/gpt-4o-mini") == "chat_completions"

    def test_realtime_models_use_realtime_api(self):
        for model in LLM_V2V_MODELS:
            if model.provider == "openai":
                assert model.api_kind == "realtime"
            if model.provider == "google":
                assert model.api_kind == "gemini_live"

    def test_defaults_reference_catalog_models(self):
        assert get_catalog_entry(DEFAULTS["modular_llm"])
        assert get_catalog_entry(DEFAULTS["v2v_llm"])
        assert DEFAULTS["modular_llm"] in {m.value for m in LLM_MODULAR_MODELS}


class TestProviderValidation:
    async def test_text_agent_rejects_v2v_pipeline(self):
        errors = await validate_agent_pipeline_config(
            modality="text",
            pipeline_type="voice_to_voice",
            llm_model="openai/gpt-5.6-luna",
        )
        assert any("modular" in e.lower() for e in errors)

    async def test_v2v_rejects_modular_llm(self):
        errors = await validate_agent_pipeline_config(
            modality="voice",
            pipeline_type="voice_to_voice",
            llm_model="openai/gpt-5.6-luna",
            tts_voice="coral",
        )
        assert any("voice-to-voice" in e.lower() for e in errors)

    async def test_modular_openai_config_valid(self):
        errors = await validate_agent_pipeline_config(
            modality="voice",
            pipeline_type="modular",
            llm_model="openai/gpt-5.6-luna",
            stt_provider="openai",
            stt_model="gpt-realtime-whisper",
            tts_provider="openai",
            tts_model="gpt-4o-mini-tts",
            tts_voice="alloy",
        )
        assert errors == []

    async def test_invalid_stt_model_rejected(self):
        errors = await validate_agent_pipeline_config(
            modality="voice",
            pipeline_type="modular",
            llm_model="openai/gpt-4o-mini",
            stt_provider="openai",
            stt_model="not-a-real-model",
            tts_provider="openai",
            tts_model="gpt-4o-mini-tts",
            tts_voice="alloy",
        )
        assert any("STT model" in e for e in errors)


class TestCatalogAPI:
    async def test_get_catalog(self, client: AsyncClient):
        resp = await client.get("/api/settings/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert "defaults" in data
        assert "llm_modular" in data
        assert "llm_v2v" in data
        assert "stt_providers" in data
        assert "tts_providers" in data
        assert isinstance(data["llm_modular"], list)
        assert any(m["value"] == "openai/gpt-5.6-luna" for m in data["llm_modular"])

    async def test_smoke_test_dry_run(self, client: AsyncClient):
        resp = await client.post("/api/settings/smoke-test", json={"live": False})
        assert resp.status_code == 200
        data = resp.json()
        assert data["live"] is False
        assert data["total"] > 0
        assert data["failed"] == 0


class TestSmokeContract:
    async def test_dry_run_covers_catalog(self):
        result = await run_configured_smoke_tests(live=False)
        assert result["total"] > 0
        assert result["passed"] == result["total"]
