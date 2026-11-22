"""Helpers for OpenAI-compatible proxy model identifiers."""

from __future__ import annotations


def litellm_model_id(model: str) -> str:
    """Return the LiteLLM model ID for an OpenAI-compatible endpoint.

    LiteLLM needs the ``openai/`` provider prefix when it is calling a
    generic OpenAI-compatible URL. Keep it when the proxy model already has
    it, otherwise add it once.
    """
    model = model.strip()
    if model.startswith("openai/"):
        return model
    return f"openai/{model}"
