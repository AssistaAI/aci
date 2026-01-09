"""Add triggers and trigger_events tables

Revision ID: a1b2c3d4e5f6
Revises: 48bf142a794c
Create Date: 2025-10-10 10:30:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '48bf142a794c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create triggers table
    op.create_table(
        'triggers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('app_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('linked_account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('trigger_name', sa.String(length=255), nullable=False),
        sa.Column('trigger_type', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('webhook_url', sa.String(length=255), nullable=False),
        sa.Column('external_webhook_id', sa.String(length=255), nullable=True),
        sa.Column('verification_token', sa.String(length=255), nullable=False),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('last_triggered_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.ForeignKeyConstraint(['app_id'], ['apps.id'], ),
        sa.ForeignKeyConstraint(['linked_account_id'], ['linked_accounts.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for triggers table
    op.create_index('ix_triggers_project_id', 'triggers', ['project_id'])
    op.create_index('ix_triggers_app_id', 'triggers', ['app_id'])
    op.create_index('ix_triggers_status', 'triggers', ['status'])
    op.create_index('ix_triggers_expires_at', 'triggers', ['expires_at'])

    # Create trigger_events table
    op.create_table(
        'trigger_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('trigger_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(length=255), nullable=False),
        sa.Column('event_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('external_event_id', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('received_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('delivered_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['trigger_id'], ['triggers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('trigger_id', 'external_event_id', name='uc_trigger_external_event')
    )

    # Create indexes for trigger_events table
    op.create_index('ix_trigger_events_trigger_id', 'trigger_events', ['trigger_id'])
    op.create_index('ix_trigger_events_status', 'trigger_events', ['status'])
    op.create_index('ix_trigger_events_received_at', 'trigger_events', ['received_at'])
    op.create_index('ix_trigger_events_expires_at', 'trigger_events', ['expires_at'])


def downgrade() -> None:
    # Drop trigger_events table
    op.drop_index('ix_trigger_events_expires_at', table_name='trigger_events')
    op.drop_index('ix_trigger_events_received_at', table_name='trigger_events')
    op.drop_index('ix_trigger_events_status', table_name='trigger_events')
    op.drop_index('ix_trigger_events_trigger_id', table_name='trigger_events')
    op.drop_table('trigger_events')

    # Drop triggers table
    op.drop_index('ix_triggers_expires_at', table_name='triggers')
    op.drop_index('ix_triggers_status', table_name='triggers')
    op.drop_index('ix_triggers_app_id', table_name='triggers')
    op.drop_index('ix_triggers_project_id', table_name='triggers')
    op.drop_table('triggers')
