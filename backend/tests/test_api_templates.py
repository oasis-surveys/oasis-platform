"""
Tests for the Agent Templates API.

Templates are a one-click starter; we verify every shipped template
materialises into a valid Agent row and that the public listing
exposes enough metadata for the picker UI to render.
"""

import pytest
from httpx import AsyncClient

from app.api.templates import TEMPLATES


@pytest.fixture
async def study_id(client: AsyncClient) -> str:
    resp = await client.post("/api/studies", json={"title": "Templates Test"})
    return resp.json()["id"]


class TestListTemplates:
    async def test_returns_all_known_templates(self, client: AsyncClient):
        resp = await client.get("/api/templates")
        assert resp.status_code == 200
        body = resp.json()
        ids = {t["id"] for t in body}
        assert ids == set(TEMPLATES.keys())

    async def test_template_summary_has_required_fields(self, client: AsyncClient):
        resp = await client.get("/api/templates")
        assert resp.status_code == 200
        for t in resp.json():
            assert t["id"]
            assert t["name"]
            assert t["description"]
            assert isinstance(t["tags"], list)
            assert t["modality"] in {"voice", "text"}
            assert t["pipeline_type"] in {"modular", "voice_to_voice"}
            assert t["llm_model"]
            assert t["interview_mode"] in {"free_form", "structured"}


class TestInstantiateTemplate:
    @pytest.mark.parametrize("template_id", list(TEMPLATES.keys()))
    async def test_each_template_creates_a_valid_agent(
        self, client: AsyncClient, study_id: str, template_id: str
    ):
        resp = await client.post(
            f"/api/studies/{study_id}/agents/from-template/{template_id}",
        )
        assert resp.status_code == 201, resp.text
        agent = resp.json()
        assert agent["study_id"] == study_id
        assert agent["status"] == "active", "templates should land active"
        # Sanity: prompt + welcome should be populated for every template
        assert agent["system_prompt"]
        assert agent["welcome_message"]
        # Widget key always generated server-side
        assert agent["widget_key"]

    async def test_name_override_is_applied(
        self, client: AsyncClient, study_id: str
    ):
        resp = await client.post(
            f"/api/studies/{study_id}/agents/from-template/semi_structured_qualitative_voice",
            json={"name": "Pilot — Qual Round 3"},
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Pilot — Qual Round 3"

    async def test_unknown_template_returns_404(
        self, client: AsyncClient, study_id: str
    ):
        resp = await client.post(
            f"/api/studies/{study_id}/agents/from-template/does_not_exist",
        )
        assert resp.status_code == 404

    async def test_unknown_study_returns_404(self, client: AsyncClient):
        bogus = "00000000-0000-0000-0000-000000000000"
        resp = await client.post(
            f"/api/studies/{bogus}/agents/from-template/semi_structured_qualitative_voice",
        )
        assert resp.status_code == 404

    async def test_structured_topic_guide_carries_interview_guide(
        self, client: AsyncClient, study_id: str
    ):
        """The structured topic-guide template ships with a real interview
        guide so it actually exercises the structured-mode pipeline
        (build_structured_prompt + InterviewGuideProcessor)."""
        resp = await client.post(
            f"/api/studies/{study_id}/agents/from-template/structured_topic_guide_voice",
        )
        assert resp.status_code == 201
        agent = resp.json()
        assert agent["interview_mode"] == "structured"
        guide = agent["interview_guide"]
        assert guide is not None
        assert len(guide["questions"]) >= 2
        for q in guide["questions"]:
            assert q["text"]
            assert isinstance(q["probes"], list)
            assert q["probes"], "every question should ship with at least one probe"
        assert guide.get("closing_message")

    async def test_cognitive_pretest_template_embeds_items_in_prompt(
        self, client: AsyncClient, study_id: str
    ):
        """
        The cognitive interview template embeds its survey items, probes,
        and verbatim instruction directly in the system prompt instead of
        using the structured-mode guide. This avoids the structured prompt
        wrapper, which tells the model to *paraphrase* questions, the exact
        opposite of what a cognitive pretest needs.
        """
        resp = await client.post(
            f"/api/studies/{study_id}/agents/from-template/cognitive_interview_pretest_voice",
        )
        assert resp.status_code == 201
        agent = resp.json()
        # FREE_FORM lets the verbatim instructions in the prompt take
        # effect without being overridden by the structured wrapper.
        assert agent["interview_mode"] == "free_form"
        assert agent["interview_guide"] is None

        prompt = agent["system_prompt"].lower()
        # Verbatim/word-for-word instruction must be present somewhere.
        assert "word for word" in prompt or "verbatim" in prompt
        # And the prompt must actually contain example items + probes.
        assert "comprehension" in prompt
        assert "recall" in prompt
        assert "judgment" in prompt
        assert "response" in prompt

    async def test_text_template_skips_voice_concerns(
        self, client: AsyncClient, study_id: str
    ):
        resp = await client.post(
            f"/api/studies/{study_id}/agents/from-template/open_ended_followup_text",
        )
        assert resp.status_code == 201
        agent = resp.json()
        assert agent["modality"] == "text"
        # Text agent shouldn't require silence handling or a TTS voice.
        assert agent["silence_timeout_seconds"] is None
        assert agent["tts_voice"] is None

    async def test_v2v_template_uses_voice_to_voice_pipeline(
        self, client: AsyncClient, study_id: str
    ):
        resp = await client.post(
            f"/api/studies/{study_id}/agents/from-template/telephone_survey_v2v",
        )
        assert resp.status_code == 201
        agent = resp.json()
        assert agent["pipeline_type"] == "voice_to_voice"
        assert agent["llm_model"].startswith("openai/gpt-realtime")

    async def test_creating_two_templates_yields_distinct_widget_keys(
        self, client: AsyncClient, study_id: str
    ):
        a = await client.post(
            f"/api/studies/{study_id}/agents/from-template/semi_structured_qualitative_voice",
        )
        b = await client.post(
            f"/api/studies/{study_id}/agents/from-template/semi_structured_qualitative_voice",
        )
        assert a.json()["widget_key"] != b.json()["widget_key"]
        assert a.json()["id"] != b.json()["id"]
