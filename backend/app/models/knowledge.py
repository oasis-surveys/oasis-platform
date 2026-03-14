"""
OASIS — Knowledge Base models for RAG.

A KnowledgeDocument represents a file/text uploaded by the researcher
to provide study context to the AI agent.

KnowledgeChunk stores individual text chunks with their vector embeddings
for similarity search during interviews.
"""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from app.models.base import Base

# OpenAI text-embedding-3-small produces 1536-dimensional vectors
EMBEDDING_DIMENSIONS = 1536


class KnowledgeDocument(Base):
    """A document uploaded to a study's knowledge base."""

    __tablename__ = "knowledge_documents"

    # ── Ownership ──
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("studies.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ── Metadata ──
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="text"
    )  # "text", "file", "url"
    content_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Relationships ──
    study = relationship(
        "Study",
        backref=backref("knowledge_documents", cascade="all, delete-orphan", passive_deletes=True),
    )
    chunks = relationship(
        "KnowledgeChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="KnowledgeChunk.chunk_index",
    )


class KnowledgeChunk(Base):
    """A text chunk with its vector embedding for similarity search."""

    __tablename__ = "knowledge_chunks"

    # ── Ownership ──
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ── Content ──
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Vector embedding (1536 dimensions for text-embedding-3-small) ──
    embedding = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=True)

    # ── Relationships ──
    document = relationship("KnowledgeDocument", back_populates="chunks")
