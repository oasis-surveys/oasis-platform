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

    async def test_voice_webhook_routes_by_to_number(self, client: AsyncClient):
        """When the To number matches another agent, that agent's id is used."""
        resp = await client.post("/api/studies", json={"title": "Twilio To Routing"})
        study_id = resp.json()["id"]

        # Two active agents, distinct Twilio numbers
        a_resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={
                "name": "Agent A",
                "status": "active",
                "twilio_phone_number": "+15551110000",
            },
        )
        a_id = a_resp.json()["id"]

        b_resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={
                "name": "Agent B",
                "status": "active",
                "twilio_phone_number": "+15552220000",
            },
        )
        b_id = b_resp.json()["id"]

        # Call agent A's URL but with To=Agent B's number → should resolve to B
        resp = await client.post(
            f"/api/twilio/voice/{a_id}",
            data="From=%2B15559876543&To=%2B15552220000&CallSid=CA0001",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 200
        assert b_id in resp.text
        assert a_id not in resp.text or resp.text.count(a_id) == 0

    async def test_voice_webhook_to_number_normalization(self, client: AsyncClient):
        """Routing should ignore spaces / dashes in the To number."""
        resp = await client.post("/api/studies", json={"title": "Twilio Normalize"})
        study_id = resp.json()["id"]

        a_resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={
                "name": "Agent X",
                "status": "active",
                "twilio_phone_number": "+1 (555) 333-0000",
            },
        )
        a_id = a_resp.json()["id"]

        resp = await client.post(
            f"/api/twilio/voice/{uuid.uuid4()}",
            data="From=%2B15559876543&To=%2B15553330000",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 200
        assert a_id in resp.text


class TestNormalizeE164:
    def test_basic(self):
        from app.api.twilio import _normalize_e164

        assert _normalize_e164("+15551234567") == "+15551234567"
        assert _normalize_e164("15551234567") == "+15551234567"
        assert _normalize_e164("+1 (555) 123-4567") == "+15551234567"
        assert _normalize_e164("") == ""
        assert _normalize_e164(None) == ""
