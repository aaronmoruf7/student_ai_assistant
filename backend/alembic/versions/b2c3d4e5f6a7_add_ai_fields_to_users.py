"""add ai_preferences and onboarding_complete to users

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-01 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('ai_preferences', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('onboarding_complete', sa.Boolean(),
                                     nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('users', 'onboarding_complete')
    op.drop_column('users', 'ai_preferences')
