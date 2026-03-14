"""
Tests for the Settings API (API key management).

Uses fake Redis from conftest — no real Redis needed.
"""

import pytest
from httpx import AsyncClient


class TestSettingsAPI:
    async def test_list_api_keys(self, client: AsyncClient):
        resp = await client.get("/api/settings/keys")
        assert resp.status_code == 200
        data = resp.json()
        assert "keys" in data
        keys = data["keys"]
        assert isinstance(keys, list)
        assert len(keys) > 0

        # Check that known fields are present
        field_names = [k["field"] for k in keys]
        assert "openai_api_key" in field_names
        assert "deepgram_api_key" in field_names
        assert "elevenlabs_api_key" in field_names

    async def test_api_key_status_fields(self, client: AsyncClient):
        resp = await client.get("/api/settings/keys")
        data = resp.json()
        key = data["keys"][0]

        assert "field" in key
        assert "env_var" in key
        assert "is_set" in key
        assert "source" in key
        assert "masked_value" in key
        assert key["source"] in ("env", "dashboard", "none")

    async def test_update_api_key(self, client: AsyncClient):
        resp = await client.put(
            "/api/settings/keys",
            json={"openai_api_key": "sk-new-test-key-12345678"},
        )
        assert resp.status_code == 200
        data = resp.json()
        keys = data["keys"]
        openai_key = next(k for k in keys if k["field"] == "openai_api_key")
        assert openai_key["is_set"] is True

    async def test_clear_api_key_override(self, client: AsyncClient):
        # First set an override
        await client.put(
            "/api/settings/keys",
            json={"deepgram_api_key": "dg-override-key"},
        )

        # Then clear it with empty string
        resp = await client.put(
            "/api/settings/keys",
            json={"deepgram_api_key": ""},
        )
        assert resp.status_code == 200

    async def test_auth_config(self, client: AsyncClient):
        resp = await client.get("/api/settings/auth")
        assert resp.status_code == 200
        data = resp.json()
        assert "auth_enabled" in data
        assert "username" in data
