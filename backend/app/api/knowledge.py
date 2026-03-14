"""
SURVEYOR — Knowledge Base API endpoints.

Allows researchers to upload, list, and delete documents in a study's
knowledge base. Documents are chunked and embedded for RAG during interviews.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from loguru import logger
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime

from app.database import get_db
from app.models.knowledge import KnowledgeDocument, KnowledgeChunk
from app.knowledge.embeddings import process_document

router = APIRouter(prefix="/studies/{study_id}/knowledge", tags=["knowledge"])


# ── Schemas ──────────────────────────────────────────────────

class KnowledgeDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    study_id: uuid.UUID
    title: str
    source_type: str
    content_length: int
    chunk_count: int
    created_at: datetime


class KnowledgeUploadText(BaseModel):
    title: str
    content: str


class KnowledgeSearchRequest(BaseModel):
    query: str
    top_k: int = 5


class KnowledgeSearchResult(BaseModel):
    content: str
    title: str
    similarity: float


# ── Endpoints ────────────────────────────────────────────────

@router.get("", response_model=list[KnowledgeDocumentRead])
async def list_documents(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """List all knowledge documents for a study."""
    result = await db.execute(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.study_id == study_id)
        .order_by(KnowledgeDocument.created_at.desc())
    )
    return result.scalars().all()


@router.post("/text", response_model=KnowledgeDocumentRead, status_code=201)
async def upload_text(
    study_id: uuid.UUID,
    body: KnowledgeUploadText,
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a text document to the study's knowledge base.

    The text is automatically chunked and embedded for RAG retrieval.
    """
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty.")

    if len(body.content) > 500_000:
        raise HTTPException(
            status_code=400,
            detail="Document too large. Maximum 500,000 characters.",
        )

    try:
        doc = await process_document(
            db=db,
            study_id=study_id,
            title=body.title.strip(),
            content=body.content,
            source_type="text",
        )
        return doc
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Failed to process document: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process document: {e}")


@router.post("/file", response_model=KnowledgeDocumentRead, status_code=201)
async def upload_file(
    study_id: uuid.UUID,
    file: UploadFile = File(...),
    title: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a text file to the study's knowledge base.

    Supports .txt, .md, .csv, and similar text-based formats.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    # Read file content
    content_bytes = await file.read()

    # Try to decode as UTF-8
    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            content = content_bytes.decode("latin-1")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=400,
                detail="File encoding not supported. Please use UTF-8 or Latin-1 encoded text files.",
            )

    if not content.strip():
        raise HTTPException(status_code=400, detail="File is empty.")

    if len(content) > 500_000:
        raise HTTPException(
            status_code=400,
            detail="File too large. Maximum 500,000 characters.",
        )

    doc_title = title or file.filename

    try:
        doc = await process_document(
            db=db,
            study_id=study_id,
            title=doc_title,
            content=content,
            source_type="file",
        )
        return doc
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Failed to process file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process file: {e}")


@router.get("/{document_id}", response_model=KnowledgeDocumentRead)
async def get_document(
    study_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single knowledge document's metadata."""
    result = await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.study_id == study_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    study_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a knowledge document and all its chunks/embeddings.

    Cascade delete removes all associated KnowledgeChunks.
    """
    result = await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.study_id == study_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    await db.delete(doc)
    await db.commit()

    logger.info(f"Deleted knowledge document: {document_id} (study={study_id})")


@router.post("/search", response_model=list[KnowledgeSearchResult])
async def search_knowledge(
    study_id: uuid.UUID,
    body: KnowledgeSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Search the study's knowledge base for relevant chunks.

    Uses vector similarity (cosine distance) to find the most relevant
    text chunks. Useful for testing the RAG retrieval before using it
    in an interview.
    """
    from app.knowledge.embeddings import search_similar_chunks

    results = await search_similar_chunks(
        db=db,
        study_id=study_id,
        query=body.query,
        top_k=body.top_k,
    )
    return results
