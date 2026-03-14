"""
Tests for the Analytics API endpoint.
"""

import uuid

import pytest
from httpx import AsyncClient


class TestAnalytics:
    async def test_study_analytics_empty(self, client: AsyncClient):
        """Analytics for a study with no sessions."""
        resp = await client.post("/api/studies", json={"title": "Analytics Test"})
        study_id = resp.json()["id"]

        resp = await client.get(f"/api/studies/{study_id}/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_sessions"] == 0
        assert data["agents"] == []

    async def test_study_analytics_with_agent(self, client: AsyncClient):
        """Analytics for a study with an agent but no sessions."""
        resp = await client.post("/api/studies", json={"title": "Analytics Test 2"})
        study_id = resp.json()["id"]

        await client.post(
            f"/api/studies/{study_id}/agents",
            json={"name": "Analytics Agent"},
        )

        resp = await client.get(f"/api/studies/{study_id}/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["agents"]) == 1
        assert data["agents"][0]["agent_name"] == "Analytics Agent"
        assert data["agents"][0]["total_sessions"] == 0

    async def test_study_analytics_not_found(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/studies/{fake_id}/analytics")
        assert resp.status_code == 404
