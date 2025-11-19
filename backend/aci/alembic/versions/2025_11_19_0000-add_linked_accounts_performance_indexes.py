"""Add performance indexes for linked_accounts table

Revision ID: add_linked_accounts_perf_idx
Revises: 48bf142a794c
Create Date: 2025-11-19 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_linked_accounts_perf_idx'
down_revision: Union[str, None] = '48bf142a794c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add index for project_id filtering (most common query pattern)
    op.create_index(
        'ix_linked_accounts_project_id',
        'linked_accounts',
        ['project_id'],
        unique=False
    )

    # Add composite index for project + app filtering
    op.create_index(
        'ix_linked_accounts_project_app',
        'linked_accounts',
        ['project_id', 'app_id'],
        unique=False
    )

    # Add index for cursor-based pagination (project_id + created_at for ordering)
    op.create_index(
        'ix_linked_accounts_project_created',
        'linked_accounts',
        ['project_id', 'created_at'],
        unique=False
    )

    # Add index for enabled status filtering
    op.create_index(
        'ix_linked_accounts_enabled',
        'linked_accounts',
        ['project_id', 'enabled'],
        unique=False
    )

    # Add index for linked_account_owner_id lookups
    op.create_index(
        'ix_linked_accounts_owner_id',
        'linked_accounts',
        ['project_id', 'linked_account_owner_id'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_linked_accounts_owner_id', table_name='linked_accounts')
    op.drop_index('ix_linked_accounts_enabled', table_name='linked_accounts')
    op.drop_index('ix_linked_accounts_project_created', table_name='linked_accounts')
    op.drop_index('ix_linked_accounts_project_app', table_name='linked_accounts')
    op.drop_index('ix_linked_accounts_project_id', table_name='linked_accounts')
