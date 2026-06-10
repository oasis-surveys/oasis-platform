"""add updated_at to engagement and adaptive tables

The ``EngagementTurn``, ``EngagementEvent``, and ``AdaptiveAction`` models all
inherit ``created_at``/``updated_at`` from ``Base``, but the tables were created
without ``updated_at``. Loading these rows (e.g. for the engagement endpoint or
exports) selects ``updated_at`` and fails. This adds the missing column.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("engagement_turns", "engagement_events", "adaptive_actions")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "updated_at")
