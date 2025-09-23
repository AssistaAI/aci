"""Add FunctionSearchFeedback table for search quality tracking

Revision ID: add_search_feedback
Revises: 48bf142a794c
Create Date: 2025-01-23 12:00:00.000000

NOTE: The GIN index creation has been commented out and should be
run manually in production during low-traffic periods:

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX CONCURRENTLY ix_functions_name_trgm ON functions USING gin (name gin_trgm_ops);
CREATE INDEX CONCURRENTLY ix_functions_description_trgm ON functions USING gin (description gin_trgm_ops);
CREATE INDEX CONCURRENTLY ix_apps_name_trgm ON apps USING gin (name gin_trgm_ops);

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_search_feedback'
down_revision: Union[str, None] = '48bf142a794c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the function_search_feedback table
    op.create_table(
        'function_search_feedback',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('intent', sa.Text(), nullable=True),
        sa.Column('returned_function_names', postgresql.ARRAY(sa.String(255)), nullable=False),
        sa.Column('selected_function_name', sa.String(255), nullable=True),
        sa.Column('was_helpful', sa.Boolean(), nullable=False),
        sa.Column('feedback_type', sa.String(50), nullable=False, server_default='explicit'),
        sa.Column('feedback_comment', sa.Text(), nullable=True),
        sa.Column('search_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for better query performance
    op.create_index('ix_function_search_feedback_agent_id', 'function_search_feedback', ['agent_id'])
    op.create_index('ix_function_search_feedback_project_id', 'function_search_feedback', ['project_id'])
    op.create_index('ix_function_search_feedback_created_at', 'function_search_feedback', ['created_at'])
    op.create_index('ix_function_search_feedback_was_helpful', 'function_search_feedback', ['was_helpful'])

    # GIN indexes should be created manually in production with CONCURRENTLY option
    # to avoid locking tables. See migration docstring for commands.


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_function_search_feedback_was_helpful', 'function_search_feedback')
    op.drop_index('ix_function_search_feedback_created_at', 'function_search_feedback')
    op.drop_index('ix_function_search_feedback_project_id', 'function_search_feedback')
    op.drop_index('ix_function_search_feedback_agent_id', 'function_search_feedback')

    # Drop the table
    op.drop_table('function_search_feedback')