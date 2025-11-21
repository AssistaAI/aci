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
    op.execute("CREATE INDEX IF NOT EXISTS ix_apps_visibility ON apps (visibility)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_apps_active ON apps (active)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_apps_visibility_active ON apps (visibility, active)")

    # Functions table indexes for filtering and searching
    op.execute("CREATE INDEX IF NOT EXISTS ix_functions_visibility ON functions (visibility)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_functions_active ON functions (active)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_functions_app_id ON functions (app_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_functions_visibility_active ON functions (visibility, active)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_functions_app_id_visibility_active ON functions (app_id, visibility, active)")

    # LinkedAccounts table indexes for project-scoped queries
    op.execute("CREATE INDEX IF NOT EXISTS ix_linked_accounts_project_id ON linked_accounts (project_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_linked_accounts_app_id ON linked_accounts (app_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_linked_accounts_project_app ON linked_accounts (project_id, app_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_linked_accounts_owner_id ON linked_accounts (linked_account_owner_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_linked_accounts_enabled ON linked_accounts (enabled)")

    # AppConfigurations table indexes for project-scoped queries
    op.execute("CREATE INDEX IF NOT EXISTS ix_app_configurations_project_id ON app_configurations (project_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_app_configurations_app_id ON app_configurations (app_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_app_configurations_enabled ON app_configurations (enabled)")

    # Projects table indexes for organization-scoped queries
    op.execute("CREATE INDEX IF NOT EXISTS ix_projects_org_id ON projects (org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_projects_created_at ON projects (created_at)")

    # Agents table indexes for project-scoped queries
    op.execute("CREATE INDEX IF NOT EXISTS ix_agents_project_id ON agents (project_id)")

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
    op.execute("DROP INDEX IF EXISTS ix_agents_project_id")

    op.execute("DROP INDEX IF EXISTS ix_projects_created_at")
    op.execute("DROP INDEX IF EXISTS ix_projects_org_id")

    op.execute("DROP INDEX IF EXISTS ix_app_configurations_enabled")
    op.execute("DROP INDEX IF EXISTS ix_app_configurations_app_id")
    op.execute("DROP INDEX IF EXISTS ix_app_configurations_project_id")

    op.execute("DROP INDEX IF EXISTS ix_linked_accounts_enabled")
    op.execute("DROP INDEX IF EXISTS ix_linked_accounts_owner_id")
    op.execute("DROP INDEX IF EXISTS ix_linked_accounts_project_app")
    op.execute("DROP INDEX IF EXISTS ix_linked_accounts_app_id")
    op.execute("DROP INDEX IF EXISTS ix_linked_accounts_project_id")

    op.execute("DROP INDEX IF EXISTS ix_functions_app_id_visibility_active")
    op.execute("DROP INDEX IF EXISTS ix_functions_visibility_active")
    op.execute("DROP INDEX IF EXISTS ix_functions_app_id")
    op.execute("DROP INDEX IF EXISTS ix_functions_active")
    op.execute("DROP INDEX IF EXISTS ix_functions_visibility")

    op.execute("DROP INDEX IF EXISTS ix_apps_visibility_active")
    op.execute("DROP INDEX IF EXISTS ix_apps_active")
    op.execute("DROP INDEX IF EXISTS ix_apps_visibility")
