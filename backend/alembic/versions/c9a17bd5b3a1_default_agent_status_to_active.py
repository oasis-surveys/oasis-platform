"""default agent status to active

Revision ID: c9a17bd5b3a1
Revises: b2c3d4e5f6g7
Create Date: 2026-04-24
"""

from alembic import op
import sqlalchemy as sa


revision = "c9a17bd5b3a1"
down_revision = "b2c3d4e5f6g7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Flip the column-level default so new rows (including those inserted via
    # raw SQL or future ORM defaults that fall back on the column default)
    # land as ACTIVE. Existing rows are untouched.
    op.alter_column(
        "agents",
        "status",
        server_default="active",
        existing_type=sa.Enum(
            "draft", "active", "paused", name="agent_status"
        ),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "agents",
        "status",
        server_default="draft",
        existing_type=sa.Enum(
            "draft", "active", "paused", name="agent_status"
        ),
        existing_nullable=False,
    )
