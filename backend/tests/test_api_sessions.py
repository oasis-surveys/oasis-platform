"""
Tests for the Sessions API endpoints.

Uses the test FastAPI app with in-memory SQLite — no real DB needed.
"""

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.engagement import EngagementEvent, EngagementTurn
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


@pytest.fixture
async def session_with_engagement(db_session: AsyncSession, session_with_transcript):
    """Attach an engagement row to the user turn (sequence 2)."""
    study_id, agent_id, session_id = session_with_transcript
    row = EngagementTurn(
        id=uuid.uuid4(),
        session_id=uuid.UUID(session_id),
        transcript_sequence=2,
        response_latency_ms=600,
        voiced_ms=4000,
        word_count=5,
        char_count=21,
        speech_rate_wpm=75.0,
        filler_count=0,
        rms_energy=0.08,
        score=0.72,
        label="high",
        extras={"flags": [], "components": {"length": 0.2}},
    )
    db_session.add(row)
    db_session.add(
        EngagementEvent(
            id=uuid.uuid4(),
            session_id=uuid.UUID(session_id),
            transcript_sequence=2,
            event_type="recovery_after_dip",
            score_at_event=0.72,
            payload={},
        )
    )
    await db_session.commit()
    return study_id, agent_id, session_id


class TestEngagementAPI:
    async def test_engagement_empty(self, client: AsyncClient, session_with_transcript):
        study_id, agent_id, session_id = session_with_transcript
        resp = await client.get(
            f"/api/studies/{study_id}/agents/{agent_id}/sessions/{session_id}/engagement"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["turn_count"] == 0
        assert data["turns"] == []
        assert data["average_score"] is None

    async def test_engagement_summary(
        self, client: AsyncClient, session_with_engagement
    ):
        study_id, agent_id, session_id = session_with_engagement
        resp = await client.get(
            f"/api/studies/{study_id}/agents/{agent_id}/sessions/{session_id}/engagement"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["turn_count"] == 1
        assert data["average_score"] == 0.72
        assert data["label"] == "high"
        assert data["turns"][0]["transcript_sequence"] == 2
        assert data["turns"][0]["flags"] == []
        assert len(data["events"]) == 1
        assert data["events"][0]["event_type"] == "recovery_after_dip"

    async def test_engagement_in_csv_export(
        self, client: AsyncClient, session_with_engagement
    ):
        study_id, agent_id, _ = session_with_engagement
        resp = await client.get(
            f"/api/studies/{study_id}/agents/{agent_id}/sessions/export/csv"
        )
        assert resp.status_code == 200
        content = resp.text
        assert "engagement_score" in content  # header
        assert "engagement_events" in content  # header
        assert "0.72" in content
        assert "high" in content
        assert "recovery_after_dip" in content

    async def test_engagement_in_json_export(
        self, client: AsyncClient, session_with_engagement
    ):
        study_id, agent_id, _ = session_with_engagement
        resp = await client.get(
            f"/api/studies/{study_id}/agents/{agent_id}/sessions/export/json"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "engagement" in data[0]
        assert data[0]["engagement"]["turn_count"] == 1
        assert data[0]["engagement"]["label"] == "high"
        assert len(data[0]["engagement"]["events"]) == 1
        assert data[0]["engagement"]["events"][0]["event_type"] == "recovery_after_dip"


@pytest.fixture
async def session_with_adaptive(db_session: AsyncSession, session_with_engagement):
    """Attach an adaptive action to the engagement-enabled session."""
    from app.models.engagement import AdaptiveAction
    from app.models.session import Session as SessionModel

    study_id, agent_id, session_id = session_with_engagement
    session = await db_session.get(SessionModel, uuid.UUID(session_id))
    session.adaptive_active = True
    db_session.add(
        AdaptiveAction(
            id=uuid.uuid4(),
            session_id=uuid.UUID(session_id),
            transcript_sequence=2,
            trigger="recovery_after_dip",
            action="acknowledge_effort",
            mode="live",
            detail={"applied": True, "instruction": "Nice work."},
        )
    )
    await db_session.commit()
    return study_id, agent_id, session_id


class TestAdaptiveAPI:
    async def test_adaptive_in_engagement_endpoint(
        self, client: AsyncClient, session_with_adaptive
    ):
        study_id, agent_id, session_id = session_with_adaptive
        resp = await client.get(
            f"/api/studies/{study_id}/agents/{agent_id}/sessions/{session_id}/engagement"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["adaptive_active"] is True
        assert len(data["adaptive_actions"]) == 1
        act = data["adaptive_actions"][0]
        assert act["action"] == "acknowledge_effort"
        assert act["mode"] == "live"
        assert act["trigger"] == "recovery_after_dip"

    async def test_adaptive_in_csv_export(
        self, client: AsyncClient, session_with_adaptive
    ):
        study_id, agent_id, _ = session_with_adaptive
        resp = await client.get(
            f"/api/studies/{study_id}/agents/{agent_id}/sessions/export/csv"
        )
        assert resp.status_code == 200
        content = resp.text
        assert "adaptive_actions" in content  # header
        assert "acknowledge_effort" in content

    async def test_adaptive_in_json_export(
        self, client: AsyncClient, session_with_adaptive
    ):
        study_id, agent_id, _ = session_with_adaptive
        resp = await client.get(
            f"/api/studies/{study_id}/agents/{agent_id}/sessions/export/json"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "adaptive" in data[0]
        assert data[0]["adaptive"]["active"] is True
        assert data[0]["adaptive"]["actions"][0]["action"] == "acknowledge_effort"
