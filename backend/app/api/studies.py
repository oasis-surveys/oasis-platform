"""
SURVEYOR — Study CRUD endpoints.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
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
    """Update a study. Only provided fields are changed."""
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(study, field, value)

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
