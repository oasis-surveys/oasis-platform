"""
Tests for authentication — JWT creation, verification, login endpoint.

Uses the in-memory test fixtures from conftest. No external services needed.
"""

import time

import pytest
from httpx import AsyncClient

from app.auth import create_token, verify_token


# ── JWT Token Unit Tests ──────────────────────────────────────────

class TestJWT:
    def test_create_token(self):
        token = create_token("testuser")
        assert isinstance(token, str)
        assert len(token) > 20

    def test_verify_valid_token(self):
        token = create_token("testuser")
        payload = verify_token(token)
        assert payload is not None
        assert payload["sub"] == "testuser"

    def test_verify_invalid_token(self):
        payload = verify_token("not.a.valid.token")
        assert payload is None

    def test_verify_empty_token(self):
        payload = verify_token("")
        assert payload is None

    def test_token_contains_exp(self):
        token = create_token("admin")
        payload = verify_token(token)
        assert "exp" in payload
        assert payload["exp"] > time.time()

    def test_token_contains_iat(self):
        token = create_token("admin")
        payload = verify_token(token)
        assert "iat" in payload
        assert payload["iat"] <= time.time()


# ── Login Endpoint Tests ──────────────────────────────────────────

class TestLoginEndpoint:
    async def test_login_auth_disabled(self, client: AsyncClient):
        """When auth is disabled, any credentials should work."""
        resp = await client.post(
            "/api/auth/login",
            json={"username": "anybody", "password": "anything"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["username"] == "anybody"

    async def test_login_returns_valid_token(self, client: AsyncClient):
        resp = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        token = resp.json()["token"]
        payload = verify_token(token)
        assert payload is not None
        assert payload["sub"] == "admin"


# ── Auth Status Endpoint Tests ────────────────────────────────────

class TestAuthStatus:
    async def test_auth_status_unauthenticated(self, client: AsyncClient):
        """Auth status should return when auth is disabled."""
        resp = await client.get("/api/auth/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "auth_enabled" in data

    async def test_auth_status_authenticated(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/auth/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "auth_enabled" in data
