"""add adaptive behavior

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-06-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "adaptive_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "agents",
        sa.Column("adaptive_policy", JSONB(), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "adaptive_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.create_table(
        "adaptive_actions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("transcript_sequence", sa.Integer(), nullable=True),
        sa.Column("trigger", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("detail", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_adaptive_actions_session_id",
        "adaptive_actions",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_adaptive_actions_session_id", table_name="adaptive_actions")
    op.drop_table("adaptive_actions")
    op.drop_column("sessions", "adaptive_active")
    op.drop_column("agents", "adaptive_policy")
    op.drop_column("agents", "adaptive_enabled")
