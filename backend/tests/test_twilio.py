"""
Tests for the Twilio integration endpoints.

No Twilio account needed — all external calls are mocked.
"""

import uuid

import pytest
from httpx import AsyncClient


class TestTwilioEndpoints:
    async def test_voice_webhook_active_agent(self, client: AsyncClient):
        """The voice webhook should return TwiML that connects to a WebSocket."""
        # Create a study and agent
        resp = await client.post("/api/studies", json={"title": "Twilio Test"})
        study_id = resp.json()["id"]

        agent_resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={
                "name": "Twilio Agent",
                "status": "active",
                "twilio_phone_number": "+15551234567",
            },
        )
        agent_id = agent_resp.json()["id"]

        # Call the voice webhook
        resp = await client.post(
            f"/api/twilio/voice/{agent_id}",
            data="From=%2B15559876543&CallSid=CA1234567890",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        # Should return TwiML XML
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "xml" in content_type
        assert "<Response>" in resp.text
        assert "Stream" in resp.text

    async def test_voice_webhook_nonexistent_agent(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.post(
            f"/api/twilio/voice/{fake_id}",
            data="From=%2B15559876543",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        # Should return TwiML that says agent is unavailable (still 200)
        assert resp.status_code == 200
        assert "Sorry" in resp.text or "unavailable" in resp.text

    async def test_voice_webhook_inactive_agent(self, client: AsyncClient):
        """A draft agent should not be connectable via Twilio."""
        resp = await client.post("/api/studies", json={"title": "Twilio Inactive"})
        study_id = resp.json()["id"]

        agent_resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={"name": "Draft Agent", "status": "draft"},
        )
        agent_id = agent_resp.json()["id"]

        resp = await client.post(
            f"/api/twilio/voice/{agent_id}",
            data="From=%2B15559876543",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        # Should indicate agent is unavailable
        assert resp.status_code == 200
        assert "unavailable" in resp.text or "Sorry" in resp.text
