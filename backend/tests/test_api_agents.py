"""
Tests for the Agents CRUD API endpoints.

Uses the test FastAPI app with in-memory SQLite — no real DB needed.
"""

import uuid

import pytest
from httpx import AsyncClient


@pytest.fixture
async def study_id(client: AsyncClient) -> str:
    """Create a study and return its ID for agent tests."""
    resp = await client.post("/api/studies", json={"title": "Agent Test Study"})
    return resp.json()["id"]


class TestAgentsCRUD:
    async def test_list_agents_empty(self, client: AsyncClient, study_id: str):
        resp = await client.get(f"/api/studies/{study_id}/agents")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_agent_minimal(self, client: AsyncClient, study_id: str):
        resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={"name": "Survey Bot"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Survey Bot"
        assert data["study_id"] == study_id
        assert data["pipeline_type"] == "modular"
        assert data["llm_model"] == "openai/gpt-5.6-luna"
        assert data["stt_provider"] == "openai"
        assert data["stt_model"] == "gpt-realtime-whisper"
        assert data["tts_provider"] == "openai"
        assert data["tts_model"] == "gpt-4o-mini-tts"
        assert data["tts_voice"] == "alloy"
        assert "widget_key" in data

    async def test_create_agent_full(self, client: AsyncClient, study_id: str):
        resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={
                "name": "Full Agent",
                "system_prompt": "You are an interviewer.",
                "welcome_message": "Welcome!",
                "pipeline_type": "voice_to_voice",
                "llm_model": "openai/gpt-realtime-2.1-mini",
                "language": "en",
                "max_duration_seconds": 600,
                "status": "active",
                "widget_title": "My Survey",
                "widget_description": "Please speak clearly.",
                "widget_primary_color": "#FF0000",
                "widget_listening_message": "Listening…",
                "silence_timeout_seconds": 10,
                "silence_prompt": "Take your time.",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["pipeline_type"] == "voice_to_voice"
        assert data["llm_model"] == "openai/gpt-realtime-2.1-mini"
        assert data["max_duration_seconds"] == 600
        assert data["silence_timeout_seconds"] == 10
        assert data["silence_prompt"] == "Take your time."
        assert data["widget_listening_message"] == "Listening…"

    async def test_create_agent_with_engagement_config(self, client: AsyncClient, study_id: str):
        resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={
                "name": "Engaged Agent",
                "track_engagement": True,
                "engagement_config": {
                    "window_size": 4,
                    "low_threshold": 0.3,
                    "weights": {"length": 0.5},
                },
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["track_engagement"] is True
        assert data["engagement_config"]["window_size"] == 4
        assert data["engagement_config"]["low_threshold"] == 0.3
        # Unspecified weights fall back to schema defaults.
        assert data["engagement_config"]["weights"]["length"] == 0.5
        assert data["engagement_config"]["weights"]["latency"] == 0.25

    async def test_invalid_engagement_window_fails(self, client: AsyncClient, study_id: str):
        resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={"name": "Bad", "engagement_config": {"window_size": 99}},
        )
        assert resp.status_code == 422

    async def test_create_agent_with_adaptive_policy(self, client: AsyncClient, study_id: str):
        resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={
                "name": "Adaptive Agent",
                "track_engagement": True,
                "adaptive_enabled": True,
                "adaptive_policy": {
                    "mode": "shadow",
                    "rules": [
                        {
                            "on": "sustained_disengagement",
                            "action": "offer_break",
                            "cooldown_seconds": 90,
                        }
                    ],
                },
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["adaptive_enabled"] is True
        assert data["adaptive_policy"]["mode"] == "shadow"
        assert data["adaptive_policy"]["rules"][0]["action"] == "offer_break"

    async def test_invalid_adaptive_action_fails(self, client: AsyncClient, study_id: str):
        resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={
                "name": "Bad Adaptive",
                "adaptive_policy": {
                    "mode": "live",
                    "rules": [{"on": "long_latency", "action": "do_a_barrel_roll"}],
                },
            },
        )
        assert resp.status_code == 422

    async def test_create_agent_empty_name_fails(self, client: AsyncClient, study_id: str):
        resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={"name": ""},
        )
        assert resp.status_code == 422

    async def test_create_agent_invalid_v2v_model_fails(self, client: AsyncClient, study_id: str):
        resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={
                "name": "Bad V2V",
                "pipeline_type": "voice_to_voice",
                "llm_model": "openai/gpt-5.6-luna",
            },
        )
        assert resp.status_code == 400
        assert "voice-to-voice" in resp.json()["detail"].lower()

    async def test_create_text_agent_with_v2v_pipeline_fails(self, client: AsyncClient, study_id: str):
        resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={
                "name": "Bad Text",
                "modality": "text",
                "pipeline_type": "voice_to_voice",
            },
        )
        assert resp.status_code == 422

    async def test_create_agent_nonexistent_study(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.post(
            f"/api/studies/{fake_id}/agents",
            json={"name": "Ghost Agent"},
        )
        assert resp.status_code == 404

    async def test_get_agent(self, client: AsyncClient, study_id: str):
        create_resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={"name": "Get Me"},
        )
        agent_id = create_resp.json()["id"]

        resp = await client.get(f"/api/studies/{study_id}/agents/{agent_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Get Me"

    async def test_get_agent_not_found(self, client: AsyncClient, study_id: str):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/studies/{study_id}/agents/{fake_id}")
        assert resp.status_code == 404

    async def test_update_agent(self, client: AsyncClient, study_id: str):
        create_resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={"name": "Before Update"},
        )
        agent_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/studies/{study_id}/agents/{agent_id}",
            json={"name": "After Update", "status": "active"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "After Update"
        assert resp.json()["status"] == "active"

    async def test_update_agent_partial(self, client: AsyncClient, study_id: str):
        create_resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={"name": "Partial", "system_prompt": "Original prompt"},
        )
        agent_id = create_resp.json()["id"]

        # Only update the prompt — name should stay the same
        resp = await client.patch(
            f"/api/studies/{study_id}/agents/{agent_id}",
            json={"system_prompt": "Updated prompt"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Partial"
        assert resp.json()["system_prompt"] == "Updated prompt"

    async def test_update_agent_with_unchanged_config(self, client: AsyncClient, study_id: str):
        created = await client.post(
            f"/api/studies/{study_id}/agents",
            json={"name": "Before"},
        )
        agent = created.json()

        resp = await client.patch(
            f"/api/studies/{study_id}/agents/{agent['id']}",
            json={
                "name": "After",
                "modality": agent["modality"],
                "pipeline_type": agent["pipeline_type"],
                "llm_model": agent["llm_model"],
                "stt_provider": agent["stt_provider"],
                "stt_model": agent["stt_model"],
                "tts_provider": agent["tts_provider"],
                "tts_model": agent["tts_model"],
                "tts_voice": agent["tts_voice"],
            },
        )

        assert resp.status_code == 200
        assert resp.json()["name"] == "After"

    async def test_delete_agent(self, client: AsyncClient, study_id: str):
        create_resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={"name": "Delete Me"},
        )
        agent_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/studies/{study_id}/agents/{agent_id}")
        assert resp.status_code == 204

        # Verify gone
        get_resp = await client.get(f"/api/studies/{study_id}/agents/{agent_id}")
        assert get_resp.status_code == 404

    async def test_list_agents_with_data(self, client: AsyncClient, study_id: str):
        await client.post(f"/api/studies/{study_id}/agents", json={"name": "Agent A"})
        await client.post(f"/api/studies/{study_id}/agents", json={"name": "Agent B"})

        resp = await client.get(f"/api/studies/{study_id}/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2
        names = [a["name"] for a in data]
        assert "Agent A" in names
        assert "Agent B" in names

    async def test_agent_wrong_study_returns_404(self, client: AsyncClient, study_id: str):
        """An agent accessed via a different study's URL should return 404."""
        create_resp = await client.post(
            f"/api/studies/{study_id}/agents",
            json={"name": "Wrong Study"},
        )
        agent_id = create_resp.json()["id"]

        # Create another study
        other_study = await client.post("/api/studies", json={"title": "Other"})
        other_id = other_study.json()["id"]

        resp = await client.get(f"/api/studies/{other_id}/agents/{agent_id}")
        assert resp.status_code == 404
