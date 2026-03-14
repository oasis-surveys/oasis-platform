"""
Tests for the pipeline builder — model resolution, voice mapping, factory helpers.

All external API calls are mocked. No API keys, no external services needed.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline.runner import (
    _resolve_model_name,
    _resolve_elevenlabs_voice,
    _get_rag_tools_schema,
)


# ── Model Name Resolution ─────────────────────────────────────────

class TestResolveModelName:
    def test_strip_openai_prefix(self):
        assert _resolve_model_name("openai/gpt-4o") == "gpt-4o"

    def test_strip_openai_prefix_realtime(self):
        assert _resolve_model_name("openai/gpt-4o-realtime-preview") == "gpt-4o-realtime-preview"

    def test_no_prefix(self):
        assert _resolve_model_name("gpt-4o-mini") == "gpt-4o-mini"

    def test_google_prefix(self):
        assert _resolve_model_name("google/gemini-2.5-flash") == "gemini-2.5-flash"

    def test_scaleway_prefix(self):
        assert _resolve_model_name("scaleway/llama-3.3-70b") == "llama-3.3-70b"

    def test_azure_prefix(self):
        assert _resolve_model_name("azure/gpt-4-turbo") == "gpt-4-turbo"

    def test_gcp_prefix(self):
        assert _resolve_model_name("gcp/gemini-pro") == "gemini-pro"


# ── ElevenLabs Voice Resolution ───────────────────────────────────

class TestResolveElevenLabsVoice:
    def test_known_name(self):
        voice_id = _resolve_elevenlabs_voice("rachel")
        assert voice_id == "21m00Tcm4TlvDq8ikWAM"

    def test_known_name_case_insensitive(self):
        assert _resolve_elevenlabs_voice("Rachel") == "21m00Tcm4TlvDq8ikWAM"
        assert _resolve_elevenlabs_voice("RACHEL") == "21m00Tcm4TlvDq8ikWAM"

    def test_raw_voice_id_passthrough(self):
        raw_id = "21m00Tcm4TlvDq8ikWAM"
        assert _resolve_elevenlabs_voice(raw_id) == raw_id

    def test_unknown_name_treated_as_id(self):
        assert _resolve_elevenlabs_voice("custom-id-xyz") == "custom-id-xyz"

    def test_none_returns_default(self):
        assert _resolve_elevenlabs_voice(None) == "21m00Tcm4TlvDq8ikWAM"

    def test_empty_returns_default(self):
        assert _resolve_elevenlabs_voice("") == "21m00Tcm4TlvDq8ikWAM"

    def test_known_voices_coverage(self):
        """Verify all known voices can be resolved."""
        known = ["rachel", "domi", "bella", "antoni", "elli", "josh", "arnold",
                 "adam", "sam", "charlie", "emily", "alice", "bill", "george",
                 "lily", "sarah", "chris"]
        for name in known:
            voice_id = _resolve_elevenlabs_voice(name)
            assert len(voice_id) > 10  # Real ElevenLabs IDs are 20+ chars


# ── RAG Tools Schema ──────────────────────────────────────────────

class TestRAGToolsSchema:
    def test_schema_structure(self):
        schema = _get_rag_tools_schema()
        assert schema is not None
        assert hasattr(schema, "standard_tools")
        assert len(schema.standard_tools) == 1

    def test_tool_name(self):
        schema = _get_rag_tools_schema()
        tool = schema.standard_tools[0]
        assert tool.name == "search_knowledge_base"

    def test_tool_has_query_property(self):
        schema = _get_rag_tools_schema()
        tool = schema.standard_tools[0]
        assert "query" in tool.properties
        assert tool.properties["query"]["type"] == "string"

    def test_tool_query_is_required(self):
        schema = _get_rag_tools_schema()
        tool = schema.standard_tools[0]
        assert "query" in tool.required


# ── Build LLM (mocked) ───────────────────────────────────────────

class TestBuildLLM:
    @patch("app.pipeline.runner._get_key", new_callable=AsyncMock)
    async def test_build_openai_llm(self, mock_get_key):
        mock_get_key.return_value = "sk-test-key"
        from app.pipeline.runner import _build_llm

        with patch("pipecat.services.openai.llm.OpenAILLMService") as MockLLM:
            MockLLM.return_value = MagicMock()
            llm = await _build_llm("openai/gpt-4o-mini")
            MockLLM.assert_called_once()

    @patch("app.pipeline.runner._get_key", new_callable=AsyncMock)
    async def test_build_scaleway_llm(self, mock_get_key):
        mock_get_key.return_value = "scw-test-key"
        from app.pipeline.runner import _build_llm

        with patch("pipecat.services.openai.llm.OpenAILLMService") as MockLLM:
            MockLLM.return_value = MagicMock()
            llm = await _build_llm("scaleway/llama-3.3-70b-instruct")
            MockLLM.assert_called_once()
            # Should use scaleway base_url
            call_kwargs = MockLLM.call_args
            assert "base_url" in call_kwargs.kwargs


# ── Build STT (mocked) ───────────────────────────────────────────

class TestBuildSTT:
    @patch("app.pipeline.runner._get_key", new_callable=AsyncMock)
    async def test_build_deepgram_stt(self, mock_get_key):
        mock_get_key.return_value = "dg-test-key"
        from app.pipeline.runner import _build_stt

        # Pre-import so the module is in sys.modules for patching
        import importlib
        try:
            mod = importlib.import_module("pipecat.services.deepgram.stt")
            with patch.object(mod, "DeepgramSTTService") as MockSTT:
                MockSTT.return_value = MagicMock()
                stt = await _build_stt("deepgram", "en")
                MockSTT.assert_called_once()
        except ImportError:
            pytest.skip("deepgram pipecat service not installed")

    @patch("app.pipeline.runner._get_key", new_callable=AsyncMock)
    async def test_build_openai_stt(self, mock_get_key):
        mock_get_key.return_value = "sk-test-key"
        from app.pipeline.runner import _build_stt
        import importlib

        try:
            mod = importlib.import_module("pipecat.services.openai.stt")
            with patch.object(mod, "OpenAISTTService") as MockSTT:
                MockSTT.return_value = MagicMock()
                stt = await _build_stt("openai", "en")
                MockSTT.assert_called_once()
        except ImportError:
            pytest.skip("openai pipecat service not installed")

    async def test_unsupported_stt_raises(self):
        from app.pipeline.runner import _build_stt

        with pytest.raises(ValueError, match="Unsupported STT provider"):
            await _build_stt("unknown_provider", "en")


# ── Build TTS (mocked) ───────────────────────────────────────────

class TestBuildTTS:
    @patch("app.pipeline.runner._get_key", new_callable=AsyncMock)
    async def test_build_elevenlabs_tts(self, mock_get_key):
        mock_get_key.return_value = "el-test-key"
        from app.pipeline.runner import _build_tts
        import importlib

        try:
            mod = importlib.import_module("pipecat.services.elevenlabs.tts")
            with patch.object(mod, "ElevenLabsTTSService") as MockTTS:
                MockTTS.return_value = MagicMock()
                tts = await _build_tts("elevenlabs", "rachel", "en")
                MockTTS.assert_called_once()
        except ImportError:
            pytest.skip("elevenlabs pipecat service not installed")

    @patch("app.pipeline.runner._get_key", new_callable=AsyncMock)
    async def test_build_openai_tts(self, mock_get_key):
        mock_get_key.return_value = "sk-test-key"
        from app.pipeline.runner import _build_tts
        import importlib

        try:
            mod = importlib.import_module("pipecat.services.openai.tts")
            with patch.object(mod, "OpenAITTSService") as MockTTS:
                MockTTS.return_value = MagicMock()
                tts = await _build_tts("openai", "alloy", "en")
                MockTTS.assert_called_once()
        except ImportError:
            pytest.skip("openai pipecat service not installed")

    async def test_unsupported_tts_raises(self):
        from app.pipeline.runner import _build_tts

        with pytest.raises(ValueError, match="Unsupported TTS provider"):
            await _build_tts("unknown_provider", None, "en")
