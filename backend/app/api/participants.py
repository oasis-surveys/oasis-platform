"""
OASIS — CRUD endpoints for participant identifiers.

Pre-defined participant IDs are managed here and linked to sessions
when participants join via their unique link.
"""

import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent import Agent, ParticipantIdentifier
from app.schemas.participant import (
    ParticipantIdentifierBulkCreate,
    ParticipantIdentifierCreate,
    ParticipantIdentifierRead,
)

router = APIRouter(
    prefix="/studies/{study_id}/agents/{agent_id}/participants",
    tags=["participants"],
)


async def _get_agent_or_404(
    study_id: UUID, agent_id: UUID, db: AsyncSession
) -> Agent:
    agent = await db.get(Agent, agent_id)
    if not agent or agent.study_id != study_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.get("", response_model=list[ParticipantIdentifierRead])
async def list_participants(
    study_id: UUID,
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    await _get_agent_or_404(study_id, agent_id, db)
    result = await db.execute(
        select(ParticipantIdentifier)
        .where(ParticipantIdentifier.agent_id == agent_id)
        .order_by(ParticipantIdentifier.created_at.asc())
    )
    return result.scalars().all()


@router.post("", response_model=ParticipantIdentifierRead, status_code=201)
async def create_participant(
    study_id: UUID,
    agent_id: UUID,
    data: ParticipantIdentifierCreate,
    db: AsyncSession = Depends(get_db),
):
    await _get_agent_or_404(study_id, agent_id, db)

    # Check for duplicate
    existing = await db.execute(
        select(ParticipantIdentifier).where(
            ParticipantIdentifier.agent_id == agent_id,
            ParticipantIdentifier.identifier == data.identifier,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Identifier already exists")

    pid = ParticipantIdentifier(
        id=uuid.uuid4(),
        agent_id=agent_id,
        identifier=data.identifier,
        label=data.label,
    )
    db.add(pid)
    await db.commit()
    await db.refresh(pid)
    return pid


@router.post("/bulk", response_model=list[ParticipantIdentifierRead], status_code=201)
async def bulk_create_participants(
    study_id: UUID,
    agent_id: UUID,
    data: ParticipantIdentifierBulkCreate,
    db: AsyncSession = Depends(get_db),
):
    await _get_agent_or_404(study_id, agent_id, db)

    created = []
    for identifier in data.identifiers:
        identifier = identifier.strip()
        if not identifier:
            continue
        # Skip duplicates
        existing = await db.execute(
            select(ParticipantIdentifier).where(
                ParticipantIdentifier.agent_id == agent_id,
                ParticipantIdentifier.identifier == identifier,
            )
        )
        if existing.scalar_one_or_none():
            continue

        pid = ParticipantIdentifier(
            id=uuid.uuid4(),
            agent_id=agent_id,
            identifier=identifier,
        )
        db.add(pid)
        created.append(pid)

    await db.commit()
    for p in created:
        await db.refresh(p)
    return created


@router.delete("/{participant_id}", status_code=204)
async def delete_participant(
    study_id: UUID,
    agent_id: UUID,
    participant_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    await _get_agent_or_404(study_id, agent_id, db)
    pid = await db.get(ParticipantIdentifier, participant_id)
    if not pid or pid.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Participant identifier not found")
    await db.delete(pid)
    await db.commit()
