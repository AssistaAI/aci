"""Create schema_fixes table for tracking schema validation fix candidates

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-01-20 15:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create schema_fixes table for tracking schema validation fix candidates
    op.create_table(
        "schema_fixes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("function_id", sa.UUID(), nullable=False),
        sa.Column("property_path", sa.Text(), nullable=False),
        sa.Column("property_name", sa.String(length=255), nullable=False),
        sa.Column("property_schema", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column(
            "error_type",
            sa.Enum(
                "ADDITIONAL_PROPERTY",
                "WRONG_TYPE",
                "MISSING_REQUIRED",
                "AUTH_ERROR",
                "API_ERROR",
                name="schemafixerrortype",
                native_enum=False,
                length=50,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "APPROVED",
                "REJECTED",
                "MANUAL_REVIEW",
                "APPLIED",
                name="schemafixstatus",
                native_enum=False,
                length=50,
            ),
            nullable=False,
        ),
        sa.Column("llm_reasoning", sa.Text(), nullable=True),
        sa.Column("llm_confidence", sa.Float(), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_seen_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["function_id"], ["functions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "function_id", "property_path", "property_name", name="uc_function_property_path_name"
        ),
    )

    # Add indexes for common queries
    op.create_index("ix_schema_fixes_function_id", "schema_fixes", ["function_id"])
    op.create_index("ix_schema_fixes_status", "schema_fixes", ["status"])
    op.create_index("ix_schema_fixes_error_type", "schema_fixes", ["error_type"])
    op.create_index("ix_schema_fixes_function_status", "schema_fixes", ["function_id", "status"])


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_schema_fixes_function_status", table_name="schema_fixes")
    op.drop_index("ix_schema_fixes_error_type", table_name="schema_fixes")
    op.drop_index("ix_schema_fixes_status", table_name="schema_fixes")
    op.drop_index("ix_schema_fixes_function_id", table_name="schema_fixes")

    # Drop table
    op.drop_table("schema_fixes")
