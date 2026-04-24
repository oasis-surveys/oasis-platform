"""
Tests for Pydantic schemas — validation, serialisation, edge cases.

These are pure unit tests with no external dependencies.
"""

import pytest
from pydantic import ValidationError

from app.schemas.study import StudyCreate, StudyUpdate, StudyRead
from app.schemas.agent import AgentCreate, AgentUpdate, AgentRead
from app.schemas.session import SessionRead, TranscriptEntryRead, SessionDetailRead
from app.schemas.participant import (
    ParticipantIdentifierCreate,
    ParticipantIdentifierBulkCreate,
)
from app.schemas.analytics import AgentStats, StudyAnalytics
from app.models.study import StudyStatus
from app.models.agent import AgentStatus, PipelineType, ParticipantIdMode


# ── Study Schemas ─────────────────────────────────────────────────

class TestStudySchemas:
    def test_study_create_valid(self):
        s = StudyCreate(title="My Study")
        assert s.title == "My Study"
        assert s.status == StudyStatus.DRAFT
        assert s.description is None

    def test_study_create_with_description(self):
        s = StudyCreate(title="Test", description="A description")
        assert s.description == "A description"

    def test_study_create_empty_title_fails(self):
        with pytest.raises(ValidationError):
            StudyCreate(title="")

    def test_study_create_title_too_long(self):
        with pytest.raises(ValidationError):
            StudyCreate(title="x" * 256)

    def test_study_update_partial(self):
        u = StudyUpdate(title="New Title")
        assert u.title == "New Title"
        assert u.description is None
        assert u.status is None

    def test_study_update_status(self):
        u = StudyUpdate(status=StudyStatus.ACTIVE)
        assert u.status == StudyStatus.ACTIVE


# ── Agent Schemas ─────────────────────────────────────────────────

class TestAgentSchemas:
    def test_agent_create_minimal(self):
        a = AgentCreate(name="Agent 1")
        assert a.name == "Agent 1"
        assert a.pipeline_type == PipelineType.MODULAR
        assert a.llm_model == "openai/gpt-4o"
        assert a.stt_provider == "deepgram"
        assert a.tts_provider == "elevenlabs"
        assert a.language == "en"
        assert a.status == AgentStatus.ACTIVE

    def test_agent_create_v2v(self):
        a = AgentCreate(
            name="V2V Agent",
            pipeline_type=PipelineType.VOICE_TO_VOICE,
            llm_model="openai/gpt-4o-realtime-preview",
        )
        assert a.pipeline_type == PipelineType.VOICE_TO_VOICE
        assert a.llm_model == "openai/gpt-4o-realtime-preview"

    def test_agent_create_empty_name_fails(self):
        with pytest.raises(ValidationError):
            AgentCreate(name="")

    def test_agent_create_max_duration_valid(self):
        a = AgentCreate(name="Test", max_duration_seconds=300)
        assert a.max_duration_seconds == 300

    def test_agent_create_max_duration_too_small(self):
        with pytest.raises(ValidationError):
            AgentCreate(name="Test", max_duration_seconds=10)

    def test_agent_create_max_duration_too_large(self):
        with pytest.raises(ValidationError):
            AgentCreate(name="Test", max_duration_seconds=10000)

    def test_agent_create_with_silence_config(self):
        a = AgentCreate(
            name="Test",
            silence_timeout_seconds=15,
            silence_prompt="Are you there?",
        )
        assert a.silence_timeout_seconds == 15
        assert a.silence_prompt == "Are you there?"

    def test_agent_create_with_widget_customisation(self):
        a = AgentCreate(
            name="Test",
            widget_title="Survey Widget",
            widget_description="Please speak clearly.",
            widget_primary_color="#FF0000",
            widget_listening_message="I'm listening…",
        )
        assert a.widget_title == "Survey Widget"
        assert a.widget_primary_color == "#FF0000"
        assert a.widget_listening_message == "I'm listening…"

    def test_agent_update_partial(self):
        u = AgentUpdate(name="Updated Name")
        data = u.model_dump(exclude_unset=True)
        assert "name" in data
        assert "llm_model" not in data

    def test_agent_update_status(self):
        u = AgentUpdate(status=AgentStatus.ACTIVE)
        assert u.status == AgentStatus.ACTIVE

    def test_agent_create_twilio_phone(self):
        a = AgentCreate(name="Tel Agent", twilio_phone_number="+15551234567")
        assert a.twilio_phone_number == "+15551234567"


# ── Participant Schemas ───────────────────────────────────────────

class TestParticipantSchemas:
    def test_participant_create_valid(self):
        p = ParticipantIdentifierCreate(identifier="P001", label="Participant 1")
        assert p.identifier == "P001"
        assert p.label == "Participant 1"

    def test_participant_create_empty_id_fails(self):
        with pytest.raises(ValidationError):
            ParticipantIdentifierCreate(identifier="")

    def test_participant_bulk_create(self):
        b = ParticipantIdentifierBulkCreate(identifiers=["P001", "P002", "P003"])
        assert len(b.identifiers) == 3

    def test_participant_bulk_create_empty_fails(self):
        with pytest.raises(ValidationError):
            ParticipantIdentifierBulkCreate(identifiers=[])


# ── Analytics Schemas ─────────────────────────────────────────────

class TestAnalyticsSchemas:
    def test_agent_stats(self):
        s = AgentStats(
            agent_id="abc",
            agent_name="Test Agent",
            total_sessions=10,
            completed_sessions=8,
            error_sessions=1,
            timed_out_sessions=1,
            active_sessions=0,
            avg_duration_seconds=120.5,
            total_utterances=50,
            completion_rate=80.0,
        )
        assert s.total_sessions == 10
        assert s.completion_rate == 80.0

    def test_study_analytics(self):
        s = StudyAnalytics(
            study_id="abc",
            total_sessions=10,
            completed_sessions=8,
            error_sessions=1,
            timed_out_sessions=1,
            active_sessions=0,
            avg_duration_seconds=120.5,
            total_utterances=50,
            completion_rate=80.0,
            agents=[],
        )
        assert s.total_sessions == 10
        assert len(s.agents) == 0
