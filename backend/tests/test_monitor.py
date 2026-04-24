"""
Tests for the live transcript monitor WebSocket — focused on the auth gate.

The monitor endpoint is mounted at ``/ws/monitor/{session_id}``. When
``AUTH_ENABLED=true`` it must reject connections that do not carry a valid
JWT in the ``token`` query parameter; when ``AUTH_ENABLED=false`` it should
accept any connection.

We only test the gate itself: actual backfill and live-streaming behaviour
is exercised end-to-end in higher-level tests. Using a non-existent
session id lets us assert the WS was upgraded (server sends an in-band
error and closes 4004) vs rejected before upgrade (4401).
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import app.api.monitor as monitor_module
from app.api.monitor import router as monitor_router
from app.auth import create_token
from app.config import settings


@pytest.fixture
def app_no_lifespan(monkeypatch) -> FastAPI:
    """Minimal FastAPI app with just the monitor router and no lifespan.

    We replace ``async_session_factory`` with a stub that always yields a
    session whose ``execute`` returns no rows so the handler immediately
    sends ``Session not found`` and closes — no real DB needed.
    """
    fake_result = MagicMock()
    fake_result.scalar_one_or_none = MagicMock(return_value=None)

    fake_session = MagicMock()
    fake_session.execute = AsyncMock(return_value=fake_result)

    @asynccontextmanager
    async def _fake_factory_cm():
        yield fake_session

    def _fake_factory():
        return _fake_factory_cm()

    monkeypatch.setattr(monitor_module, "async_session_factory", _fake_factory)

    app = FastAPI()
    app.include_router(monitor_router)
    return app


@pytest.fixture
def fresh_session_id() -> str:
    """A random UUID — the session won't exist in the DB."""
    return str(uuid.uuid4())


class TestMonitorAuthDisabled:
    def test_connection_accepted_without_token(self, app_no_lifespan, fresh_session_id):
        # Default settings: auth disabled. The connection should upgrade and
        # the server should send an in-band "Session not found" error.
        assert settings.auth_enabled is False
        with TestClient(app_no_lifespan) as tc:
            with tc.websocket_connect(
                f"/ws/monitor/{fresh_session_id}"
            ) as ws:
                msg = ws.receive_json()
                assert msg["type"] == "error"
                assert "Session not found" in msg["message"]


class TestMonitorAuthEnabled:
    def setup_method(self, _method):
        self._was_enabled = settings.auth_enabled
        settings.auth_enabled = True

    def teardown_method(self, _method):
        settings.auth_enabled = self._was_enabled

    def test_missing_token_is_rejected(self, app_no_lifespan, fresh_session_id):
        with TestClient(app_no_lifespan) as tc:
            with pytest.raises(WebSocketDisconnect) as excinfo:
                with tc.websocket_connect(
                    f"/ws/monitor/{fresh_session_id}"
                ) as ws:
                    ws.receive_json()
            assert excinfo.value.code == 4401

    def test_invalid_token_is_rejected(self, app_no_lifespan, fresh_session_id):
        with TestClient(app_no_lifespan) as tc:
            with pytest.raises(WebSocketDisconnect) as excinfo:
                with tc.websocket_connect(
                    f"/ws/monitor/{fresh_session_id}?token=not-a-jwt"
                ) as ws:
                    ws.receive_json()
            assert excinfo.value.code == 4401

    def test_valid_token_passes_gate(self, app_no_lifespan, fresh_session_id):
        # Valid token → the gate accepts the upgrade. Since the session
        # doesn't exist, the server then sends an in-band error frame and
        # closes with 4004 — proving the auth gate let it through.
        token = create_token("admin")
        with TestClient(app_no_lifespan) as tc:
            with tc.websocket_connect(
                f"/ws/monitor/{fresh_session_id}?token={token}"
            ) as ws:
                msg = ws.receive_json()
                assert msg["type"] == "error"
                assert "Session not found" in msg["message"]
