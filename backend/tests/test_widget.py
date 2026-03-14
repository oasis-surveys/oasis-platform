"""
Tests for the public widget configuration endpoint.

This is a public-facing endpoint (no auth) so it's security-relevant.
"""

import uuid

import pytest
from httpx import AsyncClient


class TestWidgetEndpoint:
    async def test_widget_config_valid_key(self, client: AsyncClient):
        """Create a study + active agent, then fetch its widget config."""
        # Create study
        resp = await client.post("/api/studies", json={"title": "Widget Test"})
        study_id = resp.json()["id"]

        # Create an active agent
        agent_resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={
                "name": "Widget Agent",
                "status": "active",
                "welcome_message": "Welcome!",
                "widget_title": "Survey",
                "widget_description": "Please speak.",
                "widget_primary_color": "#000000",
                "widget_listening_message": "Listening...",
            },
        )
        agent_data = agent_resp.json()
        widget_key = agent_data.get("widget_key")

        assert widget_key is not None

        resp = await client.get(f"/api/widget/{widget_key}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["widget_key"] == widget_key
        assert data["widget_title"] == "Survey"
        assert data["widget_description"] == "Please speak."
        assert data["widget_listening_message"] == "Listening..."
        assert data["welcome_message"] == "Welcome!"

    async def test_widget_config_invalid_key(self, client: AsyncClient):
        resp = await client.get("/api/widget/nonexistent-key-xyz")
        assert resp.status_code == 404

    async def test_widget_config_draft_agent_returns_404(self, client: AsyncClient):
        """A draft agent's widget should return 404 (only active agents)."""
        resp = await client.post("/api/studies", json={"title": "Inactive Widget"})
        study_id = resp.json()["id"]

        agent_resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={"name": "Draft Agent", "status": "draft"},
        )
        widget_key = agent_resp.json().get("widget_key")

        if widget_key:
            resp = await client.get(f"/api/widget/{widget_key}")
            assert resp.status_code == 404

    async def test_widget_config_no_auth_required(self, client: AsyncClient):
        """Widget endpoint should work without auth headers."""
        resp = await client.get("/api/widget/any-key")
        # Should return 404 (not 401 or 403)
        assert resp.status_code == 404

    async def test_widget_config_returns_required_fields(self, client: AsyncClient):
        """Verify all fields needed by the frontend widget are present."""
        resp = await client.post("/api/studies", json={"title": "Field Test"})
        study_id = resp.json()["id"]

        agent_resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={"name": "Field Agent", "status": "active"},
        )
        widget_key = agent_resp.json().get("widget_key")

        if widget_key:
            resp = await client.get(f"/api/widget/{widget_key}")
            assert resp.status_code == 200
            data = resp.json()

            required_fields = [
                "widget_key",
                "widget_title",
                "widget_description",
                "widget_primary_color",
                "widget_listening_message",
                "participant_id_mode",
                "welcome_message",
                "language",
            ]
            for field in required_fields:
                assert field in data, f"Missing required field: {field}"

    async def test_widget_config_default_colors(self, client: AsyncClient):
        """Widget should have default colors even if not explicitly set."""
        resp = await client.post("/api/studies", json={"title": "Color Test"})
        study_id = resp.json()["id"]

        agent_resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={"name": "Color Agent", "status": "active"},
        )
        widget_key = agent_resp.json().get("widget_key")

        if widget_key:
            resp = await client.get(f"/api/widget/{widget_key}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["widget_primary_color"]  # Should not be empty
