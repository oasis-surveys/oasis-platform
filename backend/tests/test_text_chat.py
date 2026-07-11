"""
Tests for text-chat LLM routing (Anthropic, OpenAI EU, etc.).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_litellm_response(content: str = "Hello"):
    usage = MagicMock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 5
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


class TestCallLlm:
    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    @patch("app.api.text_chat._get_key", new_callable=AsyncMock)
    async def test_anthropic_uses_anthropic_api_key(self, mock_get_key, mock_acompletion):
        mock_get_key.side_effect = lambda field: {
            "anthropic_api_key": "sk-ant-test",
            "openai_api_key": "sk-openai",
        }.get(field, "")
        mock_acompletion.return_value = _mock_litellm_response()

        from app.api.text_chat import _call_llm

        await _call_llm(
            [{"role": "user", "content": "Hi"}],
            model="anthropic/claude-sonnet-4-6",
        )

        kwargs = mock_acompletion.call_args.kwargs
        assert kwargs["api_key"] == "sk-ant-test"
        assert kwargs["model"] == "anthropic/claude-sonnet-4-6"
        assert "api_base" not in kwargs

    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    @patch("app.api.text_chat._get_key", new_callable=AsyncMock)
    async def test_anthropic_missing_key_raises(self, mock_get_key, mock_acompletion):
        mock_get_key.return_value = ""

        from app.api.text_chat import _call_llm

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            await _call_llm(
                [{"role": "user", "content": "Hi"}],
                model="anthropic/claude-sonnet-4-6",
            )

        mock_acompletion.assert_not_called()

    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    @patch("app.api.text_chat._openai_api_base", new_callable=AsyncMock)
    @patch("app.api.text_chat._get_key", new_callable=AsyncMock)
    async def test_openai_routes_to_eu_when_flag_on(
        self, mock_get_key, mock_eu_base, mock_acompletion
    ):
        mock_get_key.return_value = "sk-openai-test"
        mock_eu_base.return_value = "https://eu.api.openai.com/v1"
        mock_acompletion.return_value = _mock_litellm_response()

        from app.api.text_chat import _call_llm

        await _call_llm(
            [{"role": "user", "content": "Hi"}],
            model="openai/gpt-4o-mini",
        )

        kwargs = mock_acompletion.call_args.kwargs
        assert kwargs["api_key"] == "sk-openai-test"
        assert kwargs["api_base"] == "https://eu.api.openai.com/v1"

    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    @patch("app.api.text_chat._openai_api_base", new_callable=AsyncMock)
    @patch("app.api.text_chat._get_key", new_callable=AsyncMock)
    async def test_openai_skips_eu_when_flag_off(
        self, mock_get_key, mock_eu_base, mock_acompletion
    ):
        mock_get_key.return_value = "sk-openai-test"
        mock_eu_base.return_value = None
        mock_acompletion.return_value = _mock_litellm_response()

        from app.api.text_chat import _call_llm

        await _call_llm(
            [{"role": "user", "content": "Hi"}],
            model="openai/gpt-4o-mini",
        )

        kwargs = mock_acompletion.call_args.kwargs
        assert "api_base" not in kwargs

    @pytest.mark.asyncio
    @patch("app.api.text_chat._call_openai_responses", new_callable=AsyncMock)
    @patch("app.api.text_chat._openai_api_base", new_callable=AsyncMock)
    @patch("app.api.text_chat._get_key", new_callable=AsyncMock)
    async def test_gpt_5_6_uses_responses_api(
        self, mock_get_key, mock_eu_base, mock_responses
    ):
        mock_get_key.return_value = "sk-openai-test"
        mock_eu_base.return_value = "https://eu.api.openai.com/v1"
        mock_responses.return_value = {
            "content": "Hello",
            "prompt_tokens": 10,
            "completion_tokens": 5,
        }

        from app.api.text_chat import _call_llm

        await _call_llm(
            [{"role": "user", "content": "Hi"}],
            model="openai/gpt-5.6-luna",
        )

        mock_responses.assert_awaited_once_with(
            [{"role": "user", "content": "Hi"}],
            "openai/gpt-5.6-luna",
            "sk-openai-test",
            "https://eu.api.openai.com/v1",
        )

    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    @patch("app.api.text_chat._openai_api_base", new_callable=AsyncMock)
    @patch("app.api.text_chat._get_key", new_callable=AsyncMock)
    async def test_anthropic_does_not_use_openai_eu_base(
        self, mock_get_key, mock_eu_base, mock_acompletion
    ):
        mock_get_key.side_effect = lambda field: {
            "anthropic_api_key": "sk-ant-test",
            "openai_api_key": "sk-openai",
        }.get(field, "")
        mock_eu_base.return_value = "https://eu.api.openai.com/v1"
        mock_acompletion.return_value = _mock_litellm_response()

        from app.api.text_chat import _call_llm

        await _call_llm(
            [{"role": "user", "content": "Hi"}],
            model="anthropic/claude-sonnet-4-6",
        )

        kwargs = mock_acompletion.call_args.kwargs
        assert "api_base" not in kwargs
