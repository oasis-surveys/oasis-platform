"""
Tests for the provider capability catalog, validation, and settings endpoints.
"""

import pytest
from httpx import AsyncClient

from app.config import settings
from app.providers.catalog import (
    DEFAULTS,
    LLM_MODULAR_MODELS,
    LLM_V2V_MODELS,
    get_catalog_entry,
    get_configured_catalog,
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

    async def test_azure_deployment_name_is_accepted(self, monkeypatch):
        monkeypatch.setattr(settings, "azure_openai_api_key", "key")
        monkeypatch.setattr(settings, "azure_openai_endpoint", "https://example.openai.azure.com/")
        monkeypatch.setattr(settings, "azure_openai_api_version", "2024-08-01-preview")

        errors = await validate_agent_pipeline_config(
            modality="text",
            pipeline_type="modular",
            llm_model="azure/gpt-4.1-uit",
        )
        assert errors == []

    async def test_azure_realtime_deployment_must_match(self, monkeypatch):
        monkeypatch.setattr(settings, "azure_openai_api_key", "key")
        monkeypatch.setattr(settings, "azure_openai_endpoint", "https://example.openai.azure.com/")
        monkeypatch.setattr(settings, "azure_openai_realtime_deployment", "gpt-realtime")

        ok = await validate_agent_pipeline_config(
            modality="voice",
            pipeline_type="voice_to_voice",
            llm_model="azure/gpt-realtime",
            tts_voice="alloy",
        )
        mismatch = await validate_agent_pipeline_config(
            modality="voice",
            pipeline_type="voice_to_voice",
            llm_model="azure/other",
            tts_voice="alloy",
        )
        assert ok == []
        assert any("gpt-realtime" in error for error in mismatch)

    async def test_azure_audio_deployments_must_match(self, monkeypatch):
        monkeypatch.setattr(settings, "azure_openai_api_key", "key")
        monkeypatch.setattr(settings, "azure_openai_endpoint", "https://example.openai.azure.com/")
        monkeypatch.setattr(settings, "azure_openai_stt_deployment", "whisper-prod")
        monkeypatch.setattr(settings, "azure_openai_tts_deployment", "tts-prod")

        errors = await validate_agent_pipeline_config(
            modality="voice",
            pipeline_type="modular",
            llm_model="azure/chat-prod",
            stt_provider="azure_openai",
            stt_model="wrong-whisper",
            tts_provider="azure_openai",
            tts_model="wrong-tts",
            tts_voice="alloy",
        )

        assert any("STT deployment" in error for error in errors)
        assert any("TTS deployment" in error for error in errors)

    async def test_self_hosted_models_accept_free_form_ids(self, monkeypatch):
        monkeypatch.setattr(settings, "self_hosted_stt_url", "http://stt.local/v1")
        monkeypatch.setattr(settings, "self_hosted_tts_url", "http://tts.local/v1")

        errors = await validate_agent_pipeline_config(
            modality="voice",
            pipeline_type="modular",
            llm_model="openai/gpt-4o-mini",
            stt_provider="self_hosted",
            stt_model="my-whisper",
            tts_provider="self_hosted",
            tts_model="my-tts",
            tts_voice="my-voice",
        )

        assert errors == []


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

    async def test_catalog_includes_configured_self_hosted_speech(
        self,
        client: AsyncClient,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "self_hosted_stt_url", "http://stt.local/v1")
        monkeypatch.setattr(settings, "self_hosted_tts_url", "http://tts.local/v1")

        resp = await client.get("/api/settings/catalog")
        data = resp.json()

        assert any(p["value"] == "self_hosted" for p in data["stt_providers"])
        assert any(p["value"] == "self_hosted" for p in data["tts_providers"])

    async def test_catalog_lists_configured_azure_deployments(self, monkeypatch):
        monkeypatch.setattr(settings, "azure_openai_api_key", "key")
        monkeypatch.setattr(settings, "azure_openai_endpoint", "https://example.openai.azure.com/")
        monkeypatch.setattr(settings, "azure_openai_api_version", "2024-08-01-preview")
        monkeypatch.setattr(settings, "azure_openai_chat_deployments", "gpt-4.1, gpt-4.1-mini")
        monkeypatch.setattr(settings, "azure_openai_stt_deployment", "whisper")
        monkeypatch.setattr(settings, "azure_openai_tts_deployment", "tts")
        monkeypatch.setattr(settings, "azure_openai_realtime_deployment", "gpt-realtime")

        data = await get_configured_catalog()

        assert any(m["value"] == "azure/gpt-4.1" for m in data["llm_text"])
        assert any(m["value"] == "azure/gpt-realtime" for m in data["llm_v2v"])
        stt = next(p for p in data["stt_providers"] if p["value"] == "azure_openai")
        tts = next(p for p in data["tts_providers"] if p["value"] == "azure_openai")
        assert stt["models"][0]["value"] == "whisper"
        assert tts["models"][0]["value"] == "tts"
        assert data["supports_custom_llm"] is True
        assert data["voices"]["openai_tts"]
        assert data["voices"]["openai_realtime"]


class TestSmokeContract:
    async def test_dry_run_covers_catalog(self):
        result = await run_configured_smoke_tests(live=False)
        assert result["total"] > 0
        assert result["passed"] == result["total"]

    async def test_dry_run_covers_self_hosted_speech(self, monkeypatch):
        monkeypatch.setattr(settings, "self_hosted_stt_url", "http://stt.local/v1")
        monkeypatch.setattr(settings, "self_hosted_tts_url", "http://tts.local/v1")

        result = await run_configured_smoke_tests(live=False)
        probes = {
            (probe["category"], probe["provider"])
            for probe in result["results"]
        }

        assert ("stt", "self_hosted") in probes
        assert ("tts", "self_hosted") in probes

    async def test_dry_run_covers_configured_azure(self, monkeypatch):
        monkeypatch.setattr(settings, "azure_openai_api_key", "key")
        monkeypatch.setattr(settings, "azure_openai_endpoint", "https://example.openai.azure.com/")
        monkeypatch.setattr(settings, "azure_openai_chat_deployments", "chat-prod")
        monkeypatch.setattr(settings, "azure_openai_stt_deployment", "whisper-prod")
        monkeypatch.setattr(settings, "azure_openai_tts_deployment", "tts-prod")
        monkeypatch.setattr(settings, "azure_openai_realtime_deployment", "realtime-prod")

        result = await run_configured_smoke_tests(live=False)
        probes = {
            (probe["category"], probe["model"])
            for probe in result["results"]
        }

        assert ("llm", "azure/chat-prod") in probes
        assert ("v2v", "azure/realtime-prod") in probes
        assert ("stt", "whisper-prod") in probes
        assert ("tts", "tts-prod") in probes
