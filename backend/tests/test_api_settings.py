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


class TestFlagsAPI:
    """Tests for the boolean feature flag endpoints (data residency, etc.)."""

    async def test_list_flags(self, client: AsyncClient):
        resp = await client.get("/api/settings/flags")
        assert resp.status_code == 200
        data = resp.json()
        assert "flags" in data
        flags = data["flags"]
        assert isinstance(flags, list)
        names = [f["field"] for f in flags]
        assert "openai_use_eu" in names

    async def test_flag_default_is_off(self, client: AsyncClient):
        resp = await client.get("/api/settings/flags")
        flag = next(f for f in resp.json()["flags"] if f["field"] == "openai_use_eu")
        assert flag["enabled"] is False
        assert flag["source"] in ("env", "default")
        assert flag["env_var"] == "OPENAI_USE_EU"

    async def test_enable_flag_via_dashboard(self, client: AsyncClient):
        resp = await client.put(
            "/api/settings/flags",
            json={"openai_use_eu": True},
        )
        assert resp.status_code == 200
        flag = next(f for f in resp.json()["flags"] if f["field"] == "openai_use_eu")
        assert flag["enabled"] is True
        assert flag["source"] == "dashboard"

    async def test_disable_flag_via_dashboard(self, client: AsyncClient):
        # Enable then disable — both should land as dashboard overrides.
        await client.put("/api/settings/flags", json={"openai_use_eu": True})
        resp = await client.put(
            "/api/settings/flags",
            json={"openai_use_eu": False},
        )
        flag = next(f for f in resp.json()["flags"] if f["field"] == "openai_use_eu")
        assert flag["enabled"] is False
        assert flag["source"] == "dashboard"

    async def test_get_effective_flag_helper(self, client: AsyncClient):
        from app.api.settings import get_effective_flag

        # Default
        assert await get_effective_flag("openai_use_eu") is False

        # Enable via API
        await client.put("/api/settings/flags", json={"openai_use_eu": True})
        assert await get_effective_flag("openai_use_eu") is True
