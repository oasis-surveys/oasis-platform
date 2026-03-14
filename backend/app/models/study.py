"""
SURVEYOR — Study model.

A Study represents a research project. Each study contains one or more Agents
that conduct the conversational interviews.
"""

import enum

from sqlalchemy import Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class StudyStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class Study(Base):
    __tablename__ = "studies"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[StudyStatus] = mapped_column(
        Enum(
            StudyStatus,
            name="study_status",
            values_callable=lambda e: [member.value for member in e],
        ),
        default=StudyStatus.DRAFT,
        server_default=StudyStatus.DRAFT.value,
    )

    # Relationships
    agents = relationship("Agent", back_populates="study", cascade="all, delete-orphan")
