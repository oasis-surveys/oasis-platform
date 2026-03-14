"""
Tests for the Participant Identifiers API endpoints.
"""

import uuid

import pytest
from httpx import AsyncClient


@pytest.fixture
async def study_agent(client: AsyncClient):
    """Create a study and agent, return (study_id, agent_id)."""
    study_resp = await client.post("/api/studies", json={"title": "Participant Test"})
    study_id = study_resp.json()["id"]

    agent_resp = await client.post(
        f"/api/studies/{study_id}/agents",
        json={
            "name": "Participant Agent",
            "participant_id_mode": "predefined",
        },
    )
    agent_id = agent_resp.json()["id"]
    return study_id, agent_id


class TestParticipantsCRUD:
    async def test_list_empty(self, client: AsyncClient, study_agent):
        study_id, agent_id = study_agent
        resp = await client.get(
            f"/api/studies/{study_id}/agents/{agent_id}/participants"
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_participant(self, client: AsyncClient, study_agent):
        study_id, agent_id = study_agent
        resp = await client.post(
            f"/api/studies/{study_id}/agents/{agent_id}/participants",
            json={"identifier": "P001", "label": "Participant 1"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["identifier"] == "P001"
        assert data["label"] == "Participant 1"
        assert data["used"] is False

    async def test_create_duplicate_fails(self, client: AsyncClient, study_agent):
        study_id, agent_id = study_agent
        await client.post(
            f"/api/studies/{study_id}/agents/{agent_id}/participants",
            json={"identifier": "P001"},
        )
        resp = await client.post(
            f"/api/studies/{study_id}/agents/{agent_id}/participants",
            json={"identifier": "P001"},
        )
        assert resp.status_code == 409

    async def test_bulk_create(self, client: AsyncClient, study_agent):
        study_id, agent_id = study_agent
        resp = await client.post(
            f"/api/studies/{study_id}/agents/{agent_id}/participants/bulk",
            json={"identifiers": ["P001", "P002", "P003"]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data) == 3

    async def test_bulk_create_skips_duplicates(self, client: AsyncClient, study_agent):
        study_id, agent_id = study_agent
        await client.post(
            f"/api/studies/{study_id}/agents/{agent_id}/participants",
            json={"identifier": "P001"},
        )
        resp = await client.post(
            f"/api/studies/{study_id}/agents/{agent_id}/participants/bulk",
            json={"identifiers": ["P001", "P002"]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data) == 1  # Only P002 is new

    async def test_delete_participant(self, client: AsyncClient, study_agent):
        study_id, agent_id = study_agent
        create_resp = await client.post(
            f"/api/studies/{study_id}/agents/{agent_id}/participants",
            json={"identifier": "P-DEL"},
        )
        pid = create_resp.json()["id"]

        resp = await client.delete(
            f"/api/studies/{study_id}/agents/{agent_id}/participants/{pid}"
        )
        assert resp.status_code == 204

    async def test_delete_nonexistent(self, client: AsyncClient, study_agent):
        study_id, agent_id = study_agent
        fake_id = str(uuid.uuid4())
        resp = await client.delete(
            f"/api/studies/{study_id}/agents/{agent_id}/participants/{fake_id}"
        )
        assert resp.status_code == 404
