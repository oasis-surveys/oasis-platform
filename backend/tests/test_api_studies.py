"""
Tests for the Studies CRUD API endpoints.

Uses the test FastAPI app with in-memory SQLite — no real DB needed.
"""

import uuid

import pytest
from httpx import AsyncClient


class TestStudiesCRUD:
    async def test_list_studies_empty(self, client: AsyncClient):
        resp = await client.get("/api/studies")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_study(self, client: AsyncClient):
        resp = await client.post(
            "/api/studies",
            json={"title": "Research Study 1", "description": "First study"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Research Study 1"
        assert data["description"] == "First study"
        assert data["status"] == "draft"
        assert "id" in data

    async def test_create_study_minimal(self, client: AsyncClient):
        resp = await client.post(
            "/api/studies",
            json={"title": "Minimal Study"},
        )
        assert resp.status_code == 201
        assert resp.json()["title"] == "Minimal Study"

    async def test_create_study_empty_title(self, client: AsyncClient):
        resp = await client.post(
            "/api/studies",
            json={"title": ""},
        )
        assert resp.status_code == 422  # Validation error

    async def test_get_study(self, client: AsyncClient):
        # Create
        create_resp = await client.post(
            "/api/studies",
            json={"title": "Get Test"},
        )
        study_id = create_resp.json()["id"]

        # Get
        resp = await client.get(f"/api/studies/{study_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == study_id
        assert resp.json()["title"] == "Get Test"

    async def test_get_study_not_found(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/studies/{fake_id}")
        assert resp.status_code == 404

    async def test_update_study(self, client: AsyncClient):
        # Create
        create_resp = await client.post(
            "/api/studies",
            json={"title": "Original Title"},
        )
        study_id = create_resp.json()["id"]

        # Update
        resp = await client.patch(
            f"/api/studies/{study_id}",
            json={"title": "Updated Title"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Title"

    async def test_update_study_status(self, client: AsyncClient):
        create_resp = await client.post(
            "/api/studies",
            json={"title": "Status Test"},
        )
        study_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/studies/{study_id}",
            json={"status": "active"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    async def test_update_study_not_found(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.patch(
            f"/api/studies/{fake_id}",
            json={"title": "Nope"},
        )
        assert resp.status_code == 404

    async def test_delete_study(self, client: AsyncClient):
        # Create
        create_resp = await client.post(
            "/api/studies",
            json={"title": "Delete Me"},
        )
        study_id = create_resp.json()["id"]

        # Delete
        resp = await client.delete(f"/api/studies/{study_id}")
        assert resp.status_code == 204

        # Verify gone
        get_resp = await client.get(f"/api/studies/{study_id}")
        assert get_resp.status_code == 404

    async def test_delete_study_not_found(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.delete(f"/api/studies/{fake_id}")
        assert resp.status_code == 404

    async def test_list_studies_returns_created(self, client: AsyncClient):
        await client.post("/api/studies", json={"title": "Study A"})
        await client.post("/api/studies", json={"title": "Study B"})

        resp = await client.get("/api/studies")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2
        titles = [s["title"] for s in data]
        assert "Study A" in titles
        assert "Study B" in titles
