"""add engagement metrics

Revision ID: e7f8a9b0c1d2
Revises: d4e5f6a7b8c9
Create Date: 2026-06-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "track_engagement",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.create_table(
        "engagement_turns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("transcript_sequence", sa.Integer(), nullable=False),
        sa.Column("response_latency_ms", sa.Integer(), nullable=True),
        sa.Column("voiced_ms", sa.Integer(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("char_count", sa.Integer(), nullable=True),
        sa.Column("speech_rate_wpm", sa.Float(), nullable=True),
        sa.Column("filler_count", sa.Integer(), nullable=True),
        sa.Column("rms_energy", sa.Float(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("label", sa.String(16), nullable=True),
        sa.Column("extras", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_engagement_turns_session_id",
        "engagement_turns",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_engagement_turns_session_id", table_name="engagement_turns")
    op.drop_table("engagement_turns")
    op.drop_column("agents", "track_engagement")
