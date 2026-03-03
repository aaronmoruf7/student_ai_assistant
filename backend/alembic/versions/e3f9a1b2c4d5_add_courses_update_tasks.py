"""add courses table and update tasks for setup flow

Revision ID: e3f9a1b2c4d5
Revises: df4d9373a3cb
Create Date: 2026-03-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e3f9a1b2c4d5'
down_revision: Union[str, None] = 'df4d9373a3cb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create courses table
    op.create_table(
        'courses',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('canvas_course_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=500), nullable=False),
        sa.Column('code', sa.String(length=100), nullable=True),
        sa.Column('term', sa.String(length=100), nullable=True),
        sa.Column('setup_complete', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('supplemental_content', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_courses_user_id'), 'courses', ['user_id'], unique=False)
    op.create_index(op.f('ix_courses_canvas_course_id'), 'courses', ['canvas_course_id'], unique=False)

    # Add new tasksource enum type
    tasksource = sa.Enum('canvas', 'extracted', 'manual', name='tasksource')
    tasksource.create(op.get_bind())

    # Add new columns to tasks
    op.add_column('tasks', sa.Column('course_id', sa.Uuid(), nullable=True))
    op.add_column('tasks', sa.Column(
        'source',
        sa.Enum('canvas', 'extracted', 'manual', name='tasksource'),
        nullable=False,
        server_default='canvas',
    ))
    op.add_column('tasks', sa.Column('confidence', sa.Float(), nullable=True))
    op.add_column('tasks', sa.Column('task_type_label', sa.String(length=255), nullable=True))

    # Create FK from tasks.course_id -> courses.id
    op.create_foreign_key(
        'fk_tasks_course_id',
        'tasks', 'courses',
        ['course_id'], ['id'],
    )
    op.create_index(op.f('ix_tasks_course_id'), 'tasks', ['course_id'], unique=False)

    # Make canvas_assignment_id, canvas_course_id, and due_at nullable
    op.alter_column('tasks', 'canvas_assignment_id',
                    existing_type=sa.Integer(),
                    nullable=True)
    op.alter_column('tasks', 'canvas_course_id',
                    existing_type=sa.Integer(),
                    nullable=True)
    op.alter_column('tasks', 'due_at',
                    existing_type=sa.DateTime(timezone=True),
                    nullable=True)


def downgrade() -> None:
    # Reverse due_at, canvas_course_id, canvas_assignment_id nullability
    op.alter_column('tasks', 'due_at',
                    existing_type=sa.DateTime(timezone=True),
                    nullable=False)
    op.alter_column('tasks', 'canvas_course_id',
                    existing_type=sa.Integer(),
                    nullable=False)
    op.alter_column('tasks', 'canvas_assignment_id',
                    existing_type=sa.Integer(),
                    nullable=False)

    op.drop_index(op.f('ix_tasks_course_id'), table_name='tasks')
    op.drop_constraint('fk_tasks_course_id', 'tasks', type_='foreignkey')
    op.drop_column('tasks', 'task_type_label')
    op.drop_column('tasks', 'confidence')
    op.drop_column('tasks', 'source')
    op.drop_column('tasks', 'course_id')

    sa.Enum(name='tasksource').drop(op.get_bind())

    op.drop_index(op.f('ix_courses_canvas_course_id'), table_name='courses')
    op.drop_index(op.f('ix_courses_user_id'), table_name='courses')
    op.drop_table('courses')
