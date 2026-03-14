"""
Tests for the Sessions API endpoints.

Uses the test FastAPI app with in-memory SQLite — no real DB needed.
"""

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session, SessionStatus, TranscriptEntry, SpeakerRole


@pytest.fixture
async def study_agent(client: AsyncClient):
    """Create a study and agent, return (study_id, agent_id)."""
    study_resp = await client.post("/api/studies", json={"title": "Session Test Study"})
    study_id = study_resp.json()["id"]

    agent_resp = await client.post(
        f"/api/studies/{study_id}/agents",
        json={"name": "Session Test Agent", "status": "active"},
    )
    agent_id = agent_resp.json()["id"]
    return study_id, agent_id


@pytest.fixture
async def session_with_transcript(db_session: AsyncSession, study_agent, client):
    """Create a session with transcript entries directly in the DB."""
    study_id, agent_id = study_agent

    session = Session(
        id=uuid.uuid4(),
        agent_id=uuid.UUID(agent_id),
        status=SessionStatus.COMPLETED,
        participant_id="test-p-001",
        duration_seconds=120.5,
        ended_at=datetime.now(timezone.utc),
    )
    db_session.add(session)
    await db_session.flush()

    entries = [
        TranscriptEntry(
            id=uuid.uuid4(),
            session_id=session.id,
            role=SpeakerRole.AGENT,
            content="Hello! Thank you for joining.",
            sequence=1,
            spoken_at=datetime.now(timezone.utc),
        ),
        TranscriptEntry(
            id=uuid.uuid4(),
            session_id=session.id,
            role=SpeakerRole.USER,
            content="Hi, happy to be here.",
            sequence=2,
            spoken_at=datetime.now(timezone.utc),
        ),
        TranscriptEntry(
            id=uuid.uuid4(),
            session_id=session.id,
            role=SpeakerRole.AGENT,
            content="Great! Let's begin.",
            sequence=3,
            spoken_at=datetime.now(timezone.utc),
        ),
    ]
    for entry in entries:
        db_session.add(entry)
    await db_session.commit()

    return study_id, agent_id, str(session.id)


class TestSessionsAPI:
    async def test_list_sessions_empty(self, client: AsyncClient, study_agent):
        study_id, agent_id = study_agent
        resp = await client.get(
            f"/api/studies/{study_id}/agents/{agent_id}/sessions"
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_session_not_found(self, client: AsyncClient, study_agent):
        study_id, agent_id = study_agent
        fake_id = str(uuid.uuid4())
        resp = await client.get(
            f"/api/studies/{study_id}/agents/{agent_id}/sessions/{fake_id}"
        )
        assert resp.status_code == 404

    async def test_get_session_with_transcript(
        self, client: AsyncClient, session_with_transcript
    ):
        study_id, agent_id, session_id = session_with_transcript
        resp = await client.get(
            f"/api/studies/{study_id}/agents/{agent_id}/sessions/{session_id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["participant_id"] == "test-p-001"
        assert len(data["entries"]) == 3
        assert data["entries"][0]["role"] == "agent"
        assert data["entries"][1]["role"] == "user"

    async def test_session_stats_empty(self, client: AsyncClient, study_agent):
        study_id, agent_id = study_agent
        resp = await client.get(
            f"/api/studies/{study_id}/agents/{agent_id}/sessions/stats/summary"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_sessions"] == 0
        assert data["completion_rate"] == 0.0

    async def test_session_stats_with_data(
        self, client: AsyncClient, session_with_transcript
    ):
        study_id, agent_id, _ = session_with_transcript
        resp = await client.get(
            f"/api/studies/{study_id}/agents/{agent_id}/sessions/stats/summary"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_sessions"] >= 1
        assert data["completed_sessions"] >= 1
        assert data["total_utterances"] >= 3

    async def test_export_csv(self, client: AsyncClient, session_with_transcript):
        study_id, agent_id, _ = session_with_transcript
        resp = await client.get(
            f"/api/studies/{study_id}/agents/{agent_id}/sessions/export/csv"
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/csv; charset=utf-8"
        content = resp.text
        assert "session_id" in content  # Header row
        assert "Hello! Thank you for joining." in content

    async def test_export_json(self, client: AsyncClient, session_with_transcript):
        study_id, agent_id, _ = session_with_transcript
        resp = await client.get(
            f"/api/studies/{study_id}/agents/{agent_id}/sessions/export/json"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert "transcript" in data[0]
        assert len(data[0]["transcript"]) == 3
