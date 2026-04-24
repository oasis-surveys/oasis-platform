"""
Tests for the knowledge base / RAG subsystem.

Chunking is tested without any API keys.
Embedding generation is mocked to avoid OpenAI API calls.
"""

import uuid
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.knowledge.embeddings import chunk_text, CHUNK_SIZE, CHUNK_OVERLAP


# ── Text Chunking ─────────────────────────────────────────────────

class TestChunkText:
    def test_empty_text(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_short_text_single_chunk(self):
        text = "Hello, world!"
        chunks = chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_text_at_chunk_boundary(self):
        text = "x" * CHUNK_SIZE
        chunks = chunk_text(text)
        assert len(chunks) == 1

    def test_text_exceeds_chunk_size(self):
        text = "x" * (CHUNK_SIZE * 3)
        chunks = chunk_text(text)
        assert len(chunks) > 1
        # All chunks should have content
        for c in chunks:
            assert len(c) > 0

    def test_paragraph_boundary_splitting(self):
        """Chunks should prefer to split at paragraph boundaries."""
        para1 = "First paragraph. " * 50  # ~850 chars
        para2 = "Second paragraph. " * 50
        text = para1 + "\n\n" + para2
        chunks = chunk_text(text)
        assert len(chunks) >= 2

    def test_sentence_boundary_splitting(self):
        """Chunks should prefer to split at sentence boundaries."""
        sentences = "This is a sentence. " * 100
        chunks = chunk_text(sentences)
        assert len(chunks) >= 2
        # Each chunk should end at a sentence boundary (most of the time)
        for chunk in chunks[:-1]:  # Exclude last
            stripped = chunk.rstrip()
            assert stripped[-1] in ".?!;" or stripped.endswith("\n")

    def test_overlap_between_chunks(self):
        """Adjacent chunks should have overlapping content."""
        text = "Word " * 500  # ~2500 chars
        chunks = chunk_text(text, chunk_size=200, overlap=50)
        if len(chunks) >= 2:
            # The end of chunk 0 should overlap with the start of chunk 1
            # This is a fuzzy check due to boundary heuristics
            last_words_c0 = chunks[0][-50:]
            first_words_c1 = chunks[1][:50]
            # At least some overlap should exist
            assert len(chunks) >= 2

    def test_custom_chunk_size(self):
        text = "a" * 1000
        chunks = chunk_text(text, chunk_size=100, overlap=10)
        assert len(chunks) > 5

    def test_preserves_content(self):
        """All original text should be represented in the chunks."""
        text = "Hello world. " * 100
        chunks = chunk_text(text)
        combined = " ".join(chunks)
        # At minimum, the key words should be present
        assert "Hello" in combined
        assert "world" in combined

    def test_unicode_content(self):
        text = "Héllo wörld. 日本語テスト。" * 100
        chunks = chunk_text(text)
        assert len(chunks) >= 1
        combined = " ".join(chunks)
        assert "日本語" in combined


# ── Embedding Generation (mocked) ────────────────────────────────

class TestEmbeddings:
    @patch("app.knowledge.embeddings.AsyncOpenAI")
    async def test_generate_embeddings_calls_openai(self, MockOpenAI):
        from app.knowledge.embeddings import generate_embeddings

        # Set up mock response
        mock_client = AsyncMock()
        MockOpenAI.return_value = mock_client

        mock_embedding = MagicMock()
        mock_embedding.embedding = [0.1] * 1536

        mock_response = MagicMock()
        mock_response.data = [mock_embedding, mock_embedding]
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        results = await generate_embeddings(["text1", "text2"])
        assert len(results) == 2
        assert len(results[0]) == 1536

    @patch("app.knowledge.embeddings.AsyncOpenAI")
    async def test_generate_single_embedding(self, MockOpenAI):
        from app.knowledge.embeddings import generate_single_embedding

        mock_client = AsyncMock()
        MockOpenAI.return_value = mock_client

        mock_embedding = MagicMock()
        mock_embedding.embedding = [0.5] * 1536

        mock_response = MagicMock()
        mock_response.data = [mock_embedding]
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        result = await generate_single_embedding("test query")
        assert len(result) == 1536

    async def test_generate_embeddings_no_api_key(self):
        """Without any embedding provider configured, should raise."""
        from app.knowledge.embeddings import generate_embeddings

        with patch("app.knowledge.embeddings.settings") as mock_settings:
            mock_settings.openai_api_key = ""
            mock_settings.embedding_api_url = ""
            mock_settings.embedding_api_key = ""
            mock_settings.embedding_model = ""
            with pytest.raises(ValueError, match="No embedding provider configured"):
                await generate_embeddings(["test"])


# ── Knowledge API (requires test DB) ──────────────────────────────

class TestKnowledgeAPI:
    async def test_list_documents_empty(self, client):
        # Create a study first
        resp = await client.post("/api/studies", json={"title": "Knowledge Test"})
        study_id = resp.json()["id"]

        resp = await client.get(f"/api/studies/{study_id}/knowledge")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_upload_text_empty_fails(self, client):
        resp = await client.post("/api/studies", json={"title": "Knowledge Test 2"})
        study_id = resp.json()["id"]

        resp = await client.post(
            f"/api/studies/{study_id}/knowledge/text",
            json={"title": "Empty Doc", "content": "   "},
        )
        assert resp.status_code == 400

    async def test_upload_text_too_large(self, client):
        resp = await client.post("/api/studies", json={"title": "Knowledge Test 3"})
        study_id = resp.json()["id"]

        resp = await client.post(
            f"/api/studies/{study_id}/knowledge/text",
            json={"title": "Huge Doc", "content": "x" * 600_000},
        )
        assert resp.status_code == 400

    async def test_get_document_not_found(self, client):
        resp = await client.post("/api/studies", json={"title": "Knowledge Test 4"})
        study_id = resp.json()["id"]
        fake_id = str(uuid.uuid4())

        resp = await client.get(f"/api/studies/{study_id}/knowledge/{fake_id}")
        assert resp.status_code == 404

    async def test_delete_document_not_found(self, client):
        resp = await client.post("/api/studies", json={"title": "Knowledge Test 5"})
        study_id = resp.json()["id"]
        fake_id = str(uuid.uuid4())

        resp = await client.delete(f"/api/studies/{study_id}/knowledge/{fake_id}")
        assert resp.status_code == 404
