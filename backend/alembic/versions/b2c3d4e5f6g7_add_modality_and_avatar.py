"""add modality and avatar fields to agents

Revision ID: b2c3d4e5f6g7
Revises: a1c2d3e4f5g6
Create Date: 2026-03-14
"""

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6g7"
down_revision = "a1c2d3e4f5g6"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Create the enum type first
    agent_modality = sa.Enum("voice", "text", name="agent_modality")
    agent_modality.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "agents",
        sa.Column(
            "modality",
            sa.Enum("voice", "text", name="agent_modality"),
            nullable=False,
            server_default="voice",
        ),
    )
    op.add_column(
        "agents",
        sa.Column("avatar", sa.String(50), nullable=True, server_default="neutral"),
    )


def downgrade() -> None:
    op.drop_column("agents", "avatar")
    op.drop_column("agents", "modality")
    sa.Enum(name="agent_modality").drop(op.get_bind(), checkfirst=True)
