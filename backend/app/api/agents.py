"""
OASIS — Agent CRUD endpoints.

Agents are nested under their parent Study.
Includes a public widget-config endpoint for the interview widget.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent import Agent, AgentStatus, ParticipantIdMode
from app.models.study import Study
from app.schemas.agent import AgentCreate, AgentList, AgentRead, AgentUpdate


# ── Public widget config schema (minimal — no secrets) ────────
class WidgetConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    widget_key: str
    widget_title: str | None
    widget_description: str | None
    widget_primary_color: str | None
    widget_listening_message: str | None
    participant_id_mode: str
    welcome_message: str | None
    language: str


router = APIRouter(prefix="/studies/{study_id}/agents", tags=["agents"])


async def _get_study_or_404(study_id: UUID, db: AsyncSession) -> Study:
    study = await db.get(Study, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    return study


@router.get("", response_model=list[AgentList])
async def list_agents(
    study_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """List all agents belonging to a study."""
    await _get_study_or_404(study_id, db)
    result = await db.execute(
        select(Agent)
        .where(Agent.study_id == study_id)
        .order_by(Agent.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def create_agent(
    study_id: UUID,
    payload: AgentCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new agent within a study."""
    await _get_study_or_404(study_id, db)
    agent = Agent(study_id=study_id, **payload.model_dump())
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(
    study_id: UUID,
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single agent by ID."""
    agent = await db.get(Agent, agent_id)
    if not agent or agent.study_id != study_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/{agent_id}", response_model=AgentRead)
async def update_agent(
    study_id: UUID,
    agent_id: UUID,
    payload: AgentUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an agent. Only provided fields are changed."""
    agent = await db.get(Agent, agent_id)
    if not agent or agent.study_id != study_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(agent, field, value)

    await db.flush()
    await db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    study_id: UUID,
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete an agent."""
    agent = await db.get(Agent, agent_id)
    if not agent or agent.study_id != study_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)
