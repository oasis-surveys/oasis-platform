"""
SURVEYOR — Embedding and chunking utilities for RAG.

Handles:
- Splitting text into manageable chunks with overlap
- Generating vector embeddings via OpenAI's text-embedding-3-small
- Searching for similar chunks via pgvector cosine distance
"""

import uuid
from typing import Optional

from loguru import logger
from openai import AsyncOpenAI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.knowledge import (
    EMBEDDING_DIMENSIONS,
    KnowledgeChunk,
    KnowledgeDocument,
)

# ── Chunking config ──────────────────────────────────────────

CHUNK_SIZE = 800       # Target chunk size in characters
CHUNK_OVERLAP = 200    # Overlap between consecutive chunks
EMBEDDING_MODEL = "text-embedding-3-small"


def chunk_text(text_content: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Split text into overlapping chunks.

    Uses paragraph boundaries where possible, falling back to
    sentence boundaries, then hard character splits.
    """
    if not text_content or not text_content.strip():
        return []

    text_content = text_content.strip()

    # If the text is short enough, return as a single chunk
    if len(text_content) <= chunk_size:
        return [text_content]

    chunks: list[str] = []
    start = 0

    while start < len(text_content):
        end = start + chunk_size

        if end >= len(text_content):
            # Last chunk — take the rest
            chunks.append(text_content[start:].strip())
            break

        # Try to break at a paragraph boundary
        segment = text_content[start:end]
        para_break = segment.rfind("\n\n")
        if para_break > chunk_size // 3:
            end = start + para_break + 2  # Include the newlines
        else:
            # Try to break at a sentence boundary
            for sep in (". ", ".\n", "? ", "! ", ";\n"):
                sent_break = segment.rfind(sep)
                if sent_break > chunk_size // 3:
                    end = start + sent_break + len(sep)
                    break

        chunk = text_content[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Move start forward with overlap
        start = max(start + 1, end - overlap)

    return chunks


# ── Embedding generation ─────────────────────────────────────

async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Generate embedding vectors for a list of texts using OpenAI.

    Returns a list of float vectors (1536 dimensions each).
    """
    if not settings.openai_api_key:
        raise ValueError(
            "OPENAI_API_KEY is required for generating embeddings. "
            "Add it to your .env file."
        )

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # OpenAI supports batching up to 2048 texts
    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )

    # Return embeddings in the same order as inputs
    embeddings = [item.embedding for item in response.data]

    logger.debug(
        f"Generated {len(embeddings)} embeddings "
        f"({EMBEDDING_DIMENSIONS}d, model={EMBEDDING_MODEL})"
    )

    return embeddings


async def generate_single_embedding(text_content: str) -> list[float]:
    """Generate a single embedding vector for a query string."""
    embeddings = await generate_embeddings([text_content])
    return embeddings[0]


# ── Document processing ──────────────────────────────────────

async def process_document(
    db: AsyncSession,
    study_id: uuid.UUID,
    title: str,
    content: str,
    source_type: str = "text",
) -> KnowledgeDocument:
    """
    Process a text document: chunk it, generate embeddings, and store
    everything in the database.

    Returns the created KnowledgeDocument.
    """
    # 1. Chunk the text
    chunks = chunk_text(content)
    if not chunks:
        raise ValueError("Document is empty or could not be chunked.")

    logger.info(
        f"Processing document '{title}': "
        f"{len(content)} chars → {len(chunks)} chunks"
    )

    # 2. Generate embeddings for all chunks in one batch
    embeddings = await generate_embeddings(chunks)

    # 3. Create the document record
    doc = KnowledgeDocument(
        study_id=study_id,
        title=title,
        source_type=source_type,
        content_length=len(content),
        chunk_count=len(chunks),
    )
    db.add(doc)
    await db.flush()  # Get the doc.id

    # 4. Create chunk records with embeddings
    for i, (chunk_text_content, embedding) in enumerate(zip(chunks, embeddings)):
        chunk = KnowledgeChunk(
            document_id=doc.id,
            content=chunk_text_content,
            chunk_index=i,
            embedding=embedding,
        )
        db.add(chunk)

    await db.commit()
    await db.refresh(doc)

    logger.info(
        f"Document '{title}' processed: id={doc.id}, "
        f"{doc.chunk_count} chunks stored with embeddings"
    )

    return doc


# ── Similarity search ────────────────────────────────────────

async def search_similar_chunks(
    db: AsyncSession,
    study_id: uuid.UUID,
    query: str,
    top_k: int = 5,
    similarity_threshold: float = 0.3,
) -> list[dict]:
    """
    Search for the most relevant knowledge chunks for a given query.

    Uses pgvector's cosine distance operator (<=>).

    Returns a list of dicts with 'content', 'title', 'similarity' keys.
    """
    # Generate embedding for the query
    query_embedding = await generate_single_embedding(query)

    # Use pgvector cosine distance for similarity search
    # Lower distance = more similar; cosine distance = 1 - cosine_similarity
    result = await db.execute(
        text("""
            SELECT
                kc.content,
                kd.title,
                1 - (kc.embedding <=> :query_embedding::vector) AS similarity
            FROM knowledge_chunks kc
            JOIN knowledge_documents kd ON kd.id = kc.document_id
            WHERE kd.study_id = :study_id
              AND kc.embedding IS NOT NULL
            ORDER BY kc.embedding <=> :query_embedding::vector
            LIMIT :top_k
        """),
        {
            "query_embedding": str(query_embedding),
            "study_id": str(study_id),
            "top_k": top_k,
        },
    )

    rows = result.fetchall()

    # Filter by similarity threshold
    results = []
    for row in rows:
        if row.similarity >= similarity_threshold:
            results.append({
                "content": row.content,
                "title": row.title,
                "similarity": round(float(row.similarity), 4),
            })

    logger.debug(
        f"RAG search for study={study_id}: "
        f"query='{query[:80]}...', "
        f"found {len(results)}/{len(rows)} chunks above threshold={similarity_threshold}"
    )

    return results
