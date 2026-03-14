"""add_structured_interview_fields

Revision ID: a1c2d3e4f5g6
Revises: 8b30eb23a410
Create Date: 2026-03-14 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c2d3e4f5g6'
down_revision: Union[str, None] = '8b30eb23a410'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Interview mode enum
    interview_mode_enum = sa.Enum(
        'free_form', 'structured',
        name='interview_mode',
    )
    interview_mode_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        'agents',
        sa.Column(
            'interview_mode',
            interview_mode_enum,
            nullable=False,
            server_default='free_form',
        ),
    )
    op.add_column(
        'agents',
        sa.Column('interview_guide', sa.JSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_column('agents', 'interview_guide')
    op.drop_column('agents', 'interview_mode')

    interview_mode_enum = sa.Enum(
        'free_form', 'structured',
        name='interview_mode',
    )
    interview_mode_enum.drop(op.get_bind(), checkfirst=True)
