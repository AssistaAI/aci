"""Add performance indexes for pagination and filtering

Revision ID: add_perf_indexes
Revises: 48bf142a794c
Create Date: 2025-11-20 12:57:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'add_perf_indexes'
down_revision: Union[str, None] = '48bf142a794c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Apps table indexes for filtering and searching
    op.create_index('ix_apps_visibility', 'apps', ['visibility'], unique=False, if_not_exists=True)
    op.create_index('ix_apps_active', 'apps', ['active'], unique=False, if_not_exists=True)
    op.create_index('ix_apps_visibility_active', 'apps', ['visibility', 'active'], unique=False, if_not_exists=True)

    # Functions table indexes for filtering and searching
    op.create_index('ix_functions_visibility', 'functions', ['visibility'], unique=False, if_not_exists=True)
    op.create_index('ix_functions_active', 'functions', ['active'], unique=False, if_not_exists=True)
    op.create_index('ix_functions_app_id', 'functions', ['app_id'], unique=False, if_not_exists=True)
    op.create_index('ix_functions_visibility_active', 'functions', ['visibility', 'active'], unique=False, if_not_exists=True)
    op.create_index('ix_functions_app_id_visibility_active', 'functions', ['app_id', 'visibility', 'active'], unique=False, if_not_exists=True)

    # LinkedAccounts table indexes for project-scoped queries
    op.create_index('ix_linked_accounts_project_id', 'linked_accounts', ['project_id'], unique=False, if_not_exists=True)
    op.create_index('ix_linked_accounts_app_id', 'linked_accounts', ['app_id'], unique=False, if_not_exists=True)
    op.create_index('ix_linked_accounts_project_app', 'linked_accounts', ['project_id', 'app_id'], unique=False, if_not_exists=True)
    op.create_index('ix_linked_accounts_owner_id', 'linked_accounts', ['linked_account_owner_id'], unique=False, if_not_exists=True)
    op.create_index('ix_linked_accounts_enabled', 'linked_accounts', ['enabled'], unique=False, if_not_exists=True)

    # AppConfigurations table indexes for project-scoped queries
    op.create_index('ix_app_configurations_project_id', 'app_configurations', ['project_id'], unique=False, if_not_exists=True)
    op.create_index('ix_app_configurations_app_id', 'app_configurations', ['app_id'], unique=False, if_not_exists=True)
    op.create_index('ix_app_configurations_enabled', 'app_configurations', ['enabled'], unique=False, if_not_exists=True)

    # Projects table indexes for organization-scoped queries
    op.create_index('ix_projects_org_id', 'projects', ['org_id'], unique=False, if_not_exists=True)
    op.create_index('ix_projects_created_at', 'projects', ['created_at'], unique=False, if_not_exists=True)

    # Agents table indexes for project-scoped queries
    op.create_index('ix_agents_project_id', 'agents', ['project_id'], unique=False, if_not_exists=True)

    # pgvector indexes for semantic search (IVFFlat with cosine distance)
    # Using lists=100 for IVFFlat partitioning (good for 10k-1M vectors)
    # Note: These indexes require the table to have data for optimal performance
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_apps_embedding ON apps "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_functions_embedding ON functions "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    # Drop pgvector indexes
    op.execute("DROP INDEX IF EXISTS ix_functions_embedding")
    op.execute("DROP INDEX IF EXISTS ix_apps_embedding")

    # Drop regular indexes in reverse order
    op.drop_index('ix_agents_project_id', table_name='agents')

    op.drop_index('ix_projects_created_at', table_name='projects')
    op.drop_index('ix_projects_org_id', table_name='projects')

    op.drop_index('ix_app_configurations_enabled', table_name='app_configurations')
    op.drop_index('ix_app_configurations_app_id', table_name='app_configurations')
    op.drop_index('ix_app_configurations_project_id', table_name='app_configurations')

    op.drop_index('ix_linked_accounts_enabled', table_name='linked_accounts')
    op.drop_index('ix_linked_accounts_owner_id', table_name='linked_accounts')
    op.drop_index('ix_linked_accounts_project_app', table_name='linked_accounts')
    op.drop_index('ix_linked_accounts_app_id', table_name='linked_accounts')
    op.drop_index('ix_linked_accounts_project_id', table_name='linked_accounts')

    op.drop_index('ix_functions_app_id_visibility_active', table_name='functions')
    op.drop_index('ix_functions_visibility_active', table_name='functions')
    op.drop_index('ix_functions_app_id', table_name='functions')
    op.drop_index('ix_functions_active', table_name='functions')
    op.drop_index('ix_functions_visibility', table_name='functions')

    op.drop_index('ix_apps_visibility_active', table_name='apps')
    op.drop_index('ix_apps_active', table_name='apps')
    op.drop_index('ix_apps_visibility', table_name='apps')
