"""add audio recording fields

Revision ID: d4e5f6a7b8c9
Revises: c9a17bd5b3a1
Create Date: 2026-05-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c9a17bd5b3a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "store_audio",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "audio_recording_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "sessions",
        sa.Column("audio_storage_uri", sa.String(1024), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "audio_recording_status",
            sa.String(32),
            nullable=False,
            server_default="none",
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "audio_recording_status")
    op.drop_column("sessions", "audio_storage_uri")
    op.drop_column("sessions", "audio_recording_enabled")
    op.drop_column("agents", "store_audio")
