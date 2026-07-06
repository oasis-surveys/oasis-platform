"""add turn_detection to agents

Per-agent turn-detection model for modular voice. "local" runs the bundled
on-device smart-turn model (pipecat 1.x default); "remote" routes to the HTTP
smart-turn endpoint configured via SMART_TURN_REMOTE_URL. Defaults to local so
existing agents keep the same behavior.

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-07-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "turn_detection",
            sa.String(length=20),
            server_default="local",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "turn_detection")
