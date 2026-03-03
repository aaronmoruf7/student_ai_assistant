"""add completed_minutes to tasks

Revision ID: a1b2c3d4e5f6
Revises: e3f9a1b2c4d5
Create Date: 2026-03-01 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'e3f9a1b2c4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tasks',
        sa.Column('completed_minutes', sa.Integer(), nullable=True, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('tasks', 'completed_minutes')
