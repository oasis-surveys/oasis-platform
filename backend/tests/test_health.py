"""
Tests for the health endpoint and basic server responses.
"""

import pytest
from httpx import AsyncClient


class TestHealth:
    async def test_health_endpoint(self, client: AsyncClient):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "healthy" in data
        assert "services" in data

    async def test_unknown_route_returns_not_found(self, client: AsyncClient):
        resp = await client.get("/api/nonexistent-endpoint-xyz")
        assert resp.status_code in (404, 405)

    async def test_json_content_type(self, client: AsyncClient):
        resp = await client.get("/api/studies")
        assert "application/json" in resp.headers.get("content-type", "")

    async def test_widget_endpoint_accessible(self, client: AsyncClient):
        """Public widget endpoint should not require auth."""
        resp = await client.get("/api/widget/any-key-here")
        assert resp.status_code == 404  # Not found, but not 401/403

    async def test_health_no_auth_required(self, client: AsyncClient):
        """Health check should work without auth."""
        resp = await client.get("/api/health")
        assert resp.status_code == 200
