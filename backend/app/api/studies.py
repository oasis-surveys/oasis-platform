"""
OASIS — Study CRUD endpoints.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent import Agent, AgentStatus
from app.models.study import Study
from app.schemas.study import StudyCreate, StudyList, StudyRead, StudyUpdate

router = APIRouter(prefix="/studies", tags=["studies"])


@router.get("", response_model=list[StudyList])
async def list_studies(db: AsyncSession = Depends(get_db)):
    """List all studies, ordered by most recently created."""
    result = await db.execute(
        select(Study).order_by(Study.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=StudyRead, status_code=status.HTTP_201_CREATED)
async def create_study(
    payload: StudyCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new study."""
    study = Study(**payload.model_dump())
    db.add(study)
    await db.flush()
    await db.refresh(study)
    return study


@router.get("/{study_id}", response_model=StudyRead)
async def get_study(study_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get a single study by ID."""
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    return study


@router.patch("/{study_id}", response_model=StudyRead)
async def update_study(
    study_id: UUID,
    payload: StudyUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a study. Only provided fields are changed.

    When the study status changes, agent statuses are cascaded:
      study → active   ⇒  draft agents → active
      study → paused   ⇒  active agents → paused
      study → completed ⇒  active/paused agents → completed
      study → draft    ⇒  no agent change
    """
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    update_data = payload.model_dump(exclude_unset=True)
    old_status = study.status
    for field, value in update_data.items():
        setattr(study, field, value)

    # ── Cascade status to agents ──────────────────────────────
    new_status = update_data.get("status")
    if new_status and new_status != old_status:
        cascade_map = {
            # new study status → (agent statuses to change, new agent status)
            "active": (
                [AgentStatus.DRAFT, AgentStatus.PAUSED],
                AgentStatus.ACTIVE,
            ),
            "paused": ([AgentStatus.ACTIVE], AgentStatus.PAUSED),
            # AgentStatus has no COMPLETED; pausing agents is the
            # closest equivalent when a study is completed.
            "completed": (
                [AgentStatus.ACTIVE],
                AgentStatus.PAUSED,
            ),
        }

        if new_status in cascade_map:
            from_statuses, to_status = cascade_map[new_status]
            result = await db.execute(
                update(Agent)
                .where(
                    Agent.study_id == study_id,
                    Agent.status.in_(from_statuses),
                )
                .values(status=to_status)
            )
            affected = result.rowcount  # type: ignore[union-attr]
            if affected:
                logger.info(
                    f"Study {study_id} → {new_status}: cascaded {affected} "
                    f"agent(s) to {to_status.value}"
                )

    await db.flush()
    await db.refresh(study)
    return study


@router.delete("/{study_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_study(study_id: UUID, db: AsyncSession = Depends(get_db)):
    """Delete a study and all its agents."""
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    await db.delete(study)
