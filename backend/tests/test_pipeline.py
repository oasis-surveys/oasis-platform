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

    @patch("app.pipeline.runner._get_key", new_callable=AsyncMock)
    async def test_build_anthropic_llm(self, mock_get_key):
        """anthropic/claude-... routes through AnthropicLLMService."""
        mock_get_key.return_value = "sk-ant-test"
        from app.pipeline.runner import _build_llm

        try:
            import importlib
            mod = importlib.import_module("pipecat.services.anthropic.llm")
        except ImportError:
            pytest.skip("anthropic pipecat service not installed")

        with patch.object(mod, "AnthropicLLMService") as MockLLM:
            MockLLM.return_value = MagicMock()
            await _build_llm("anthropic/claude-sonnet-4-5")
            MockLLM.assert_called_once()
            call_kwargs = MockLLM.call_args.kwargs
            assert call_kwargs["api_key"] == "sk-ant-test"
            # Settings dataclass should carry the model name
            assert getattr(call_kwargs["settings"], "model") == "claude-sonnet-4-5"

    @patch("app.pipeline.runner._get_key", new_callable=AsyncMock)
    async def test_build_anthropic_llm_missing_key_raises(self, mock_get_key):
        mock_get_key.return_value = ""
        from app.pipeline.runner import _build_llm

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            await _build_llm("anthropic/claude-sonnet-4-5")

    @patch("app.pipeline.runner._get_key", new_callable=AsyncMock)
    async def test_build_google_text_llm(self, mock_get_key):
        """google/gemini-... text models route through GoogleLLMService."""
        mock_get_key.return_value = "google-test"
        from app.pipeline.runner import _build_llm

        try:
            import importlib
            mod = importlib.import_module("pipecat.services.google.llm")
        except ImportError:
            pytest.skip("google pipecat service not installed")

        with patch.object(mod, "GoogleLLMService") as MockLLM:
            MockLLM.return_value = MagicMock()
            await _build_llm("google/gemini-2.5-flash")
            MockLLM.assert_called_once()
            call_kwargs = MockLLM.call_args.kwargs
            assert call_kwargs["api_key"] == "google-test"
            assert getattr(call_kwargs["settings"], "model") == "gemini-2.5-flash"

    @patch("app.pipeline.runner._get_key", new_callable=AsyncMock)
    async def test_build_google_text_llm_missing_key_raises(self, mock_get_key):
        mock_get_key.return_value = ""
        from app.pipeline.runner import _build_llm

        with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
            await _build_llm("google/gemini-2.5-flash")

    @patch("app.pipeline.runner._get_key", new_callable=AsyncMock)
    async def test_build_custom_llm(self, mock_get_key):
        """custom/<model> routes through OpenAILLMService with the configured base URL."""
        async def _key(field):
            return {
                "openai_compatible_llm_url": "http://litellm:4000/v1",
                "openai_compatible_llm_api_key": "proxy-token",
            }.get(field, "")

        mock_get_key.side_effect = _key
        from app.pipeline.runner import _build_llm

        with patch("pipecat.services.openai.llm.OpenAILLMService") as MockLLM:
            MockLLM.return_value = MagicMock()
            await _build_llm("custom/llama-3.3-70b")
            MockLLM.assert_called_once()
            call_kwargs = MockLLM.call_args.kwargs
            assert call_kwargs["base_url"] == "http://litellm:4000/v1"
            assert call_kwargs["api_key"] == "proxy-token"
            assert getattr(call_kwargs["settings"], "model") == "llama-3.3-70b"

    @patch("app.pipeline.runner._get_key", new_callable=AsyncMock)
    async def test_build_custom_llm_no_url_raises(self, mock_get_key):
        """custom/ with no URL configured (Redis or env) should error clearly."""
        mock_get_key.return_value = ""
        from app.pipeline.runner import _build_llm
        from app.config import settings as app_settings

        with patch.object(app_settings, "openai_compatible_llm_url", ""):
            with pytest.raises(ValueError, match="OPENAI_COMPATIBLE_LLM_URL"):
                await _build_llm("custom/llama-3.3-70b")

    @patch("app.pipeline.runner._get_key", new_callable=AsyncMock)
    async def test_build_custom_llm_falls_back_to_dummy_key(self, mock_get_key):
        """If no API key is set the proxy still gets a placeholder string."""
        async def _key(field):
            return {"openai_compatible_llm_url": "http://vllm:8000/v1"}.get(field, "")

        mock_get_key.side_effect = _key
        from app.pipeline.runner import _build_llm

        with patch("pipecat.services.openai.llm.OpenAILLMService") as MockLLM:
            MockLLM.return_value = MagicMock()
            await _build_llm("custom/qwen3-32b")
            assert MockLLM.call_args.kwargs["api_key"] == "not-needed"

    @patch("app.pipeline.runner._openai_use_eu", new_callable=AsyncMock)
    @patch("app.pipeline.runner._get_key", new_callable=AsyncMock)
    async def test_default_openai_llm_routes_to_eu_when_flag_on(
        self, mock_get_key, mock_use_eu
    ):
        """openai_use_eu flag injects base_url=https://eu.api.openai.com/v1."""
        mock_get_key.return_value = "sk-test"
        mock_use_eu.return_value = True
        from app.pipeline.runner import _build_llm

        with patch("pipecat.services.openai.llm.OpenAILLMService") as MockLLM:
            MockLLM.return_value = MagicMock()
            await _build_llm("openai/gpt-4o-mini")
            kwargs = MockLLM.call_args.kwargs
            assert kwargs.get("base_url") == "https://eu.api.openai.com/v1"

    @patch("app.pipeline.runner._openai_use_eu", new_callable=AsyncMock)
    @patch("app.pipeline.runner._get_key", new_callable=AsyncMock)
    async def test_default_openai_llm_skips_eu_when_flag_off(
        self, mock_get_key, mock_use_eu
    ):
        mock_get_key.return_value = "sk-test"
        mock_use_eu.return_value = False
        from app.pipeline.runner import _build_llm

        with patch("pipecat.services.openai.llm.OpenAILLMService") as MockLLM:
            MockLLM.return_value = MagicMock()
            await _build_llm("openai/gpt-4o-mini")
            kwargs = MockLLM.call_args.kwargs
            assert "base_url" not in kwargs


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

    @patch("app.pipeline.runner._openai_use_eu", new_callable=AsyncMock)
    @patch("app.pipeline.runner._get_key", new_callable=AsyncMock)
    async def test_openai_stt_routes_to_eu_when_flag_on(
        self, mock_get_key, mock_use_eu
    ):
        mock_get_key.return_value = "sk-test-key"
        mock_use_eu.return_value = True
        from app.pipeline.runner import _build_stt
        import importlib

        try:
            mod = importlib.import_module("pipecat.services.openai.stt")
            with patch.object(mod, "OpenAISTTService") as MockSTT:
                MockSTT.return_value = MagicMock()
                await _build_stt("openai", "en")
                kwargs = MockSTT.call_args.kwargs
                assert kwargs.get("base_url") == "https://eu.api.openai.com/v1"
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

    @patch("app.pipeline.runner._openai_use_eu", new_callable=AsyncMock)
    @patch("app.pipeline.runner._get_key", new_callable=AsyncMock)
    async def test_openai_tts_routes_to_eu_when_flag_on(
        self, mock_get_key, mock_use_eu
    ):
        mock_get_key.return_value = "sk-test-key"
        mock_use_eu.return_value = True
        from app.pipeline.runner import _build_tts
        import importlib

        try:
            mod = importlib.import_module("pipecat.services.openai.tts")
            with patch.object(mod, "OpenAITTSService") as MockTTS:
                MockTTS.return_value = MagicMock()
                await _build_tts("openai", "alloy", "en")
                kwargs = MockTTS.call_args.kwargs
                assert kwargs.get("base_url") == "https://eu.api.openai.com/v1"
        except ImportError:
            pytest.skip("openai pipecat service not installed")

    async def test_unsupported_tts_raises(self):
        from app.pipeline.runner import _build_tts

        with pytest.raises(ValueError, match="Unsupported TTS provider"):
            await _build_tts("unknown_provider", None, "en")


# ── OpenAI EU base URL helpers ───────────────────────────────────

class TestOpenAIEUBaseUrl:
    @patch("app.pipeline.runner._openai_use_eu", new_callable=AsyncMock)
    async def test_base_url_returns_eu_when_flag_on(self, mock_use_eu):
        mock_use_eu.return_value = True
        from app.pipeline.runner import _openai_base_url
        assert await _openai_base_url() == "https://eu.api.openai.com/v1"

    @patch("app.pipeline.runner._openai_use_eu", new_callable=AsyncMock)
    async def test_base_url_returns_none_when_flag_off(self, mock_use_eu):
        mock_use_eu.return_value = False
        from app.pipeline.runner import _openai_base_url
        assert await _openai_base_url() is None

    @patch("app.pipeline.runner._openai_use_eu", new_callable=AsyncMock)
    async def test_realtime_url_eu(self, mock_use_eu):
        mock_use_eu.return_value = True
        from app.pipeline.runner import _openai_realtime_base_url
        assert (
            await _openai_realtime_base_url()
            == "wss://eu.api.openai.com/v1/realtime"
        )

    @patch("app.pipeline.runner._openai_use_eu", new_callable=AsyncMock)
    async def test_realtime_url_default(self, mock_use_eu):
        mock_use_eu.return_value = False
        from app.pipeline.runner import _openai_realtime_base_url
        assert (
            await _openai_realtime_base_url()
            == "wss://api.openai.com/v1/realtime"
        )


# ── V2V welcome message handling ─────────────────────────────────

class TestV2VSystemPromptWithWelcome:
    """The V2V pipelines bake the welcome into the system prompt so the
    model speaks it on its own first turn instead of treating it as user
    input (the old behaviour produced 'all over the place' greetings)."""

    def test_no_welcome_returns_prompt_unchanged(self):
        from app.pipeline.runner import _v2v_system_prompt_with_welcome
        prompt = "You are a research interviewer."
        assert _v2v_system_prompt_with_welcome(prompt, None) == prompt
        assert _v2v_system_prompt_with_welcome(prompt, "") == prompt

    def test_welcome_is_appended_with_verbatim_directive(self):
        from app.pipeline.runner import _v2v_system_prompt_with_welcome
        prompt = "You are a research interviewer."
        welcome = "Hi, this is the research team calling about the study."
        out = _v2v_system_prompt_with_welcome(prompt, welcome)

        # Original prompt is preserved.
        assert prompt in out
        # The welcome line ends up inside the directive, verbatim.
        assert welcome in out
        # Directive must explicitly tell the model to speak it before
        # anything else, so it doesn't react to it as user input.
        lower = out.lower()
        assert "exactly as written" in lower or "word for word" in lower
        assert "wait for the participant" in lower


# ── V2V silence idle processor ───────────────────────────────────

class TestV2VIdleProcessor:
    """The V2V pipelines now opt-in to silence handling via _build_v2v_idle_processor."""

    def test_returns_none_when_disabled(self):
        from app.pipeline.runner import _build_v2v_idle_processor
        assert _build_v2v_idle_processor(None, "irrelevant") is None
        assert _build_v2v_idle_processor(0, "irrelevant") is None

    def test_returns_processor_when_enabled(self):
        from app.pipeline.runner import _build_v2v_idle_processor
        from pipecat.processors.user_idle_processor import UserIdleProcessor

        proc = _build_v2v_idle_processor(15, "Take your time.")
        assert proc is not None
        assert isinstance(proc, UserIdleProcessor)

    def test_falls_back_to_default_prompt(self):
        # We don't poke the internal callback (Pipecat may evolve), but we do
        # want to be sure the helper accepts a None prompt and still returns a
        # processor instead of crashing.
        from app.pipeline.runner import _build_v2v_idle_processor
        proc = _build_v2v_idle_processor(20, None)
        assert proc is not None
