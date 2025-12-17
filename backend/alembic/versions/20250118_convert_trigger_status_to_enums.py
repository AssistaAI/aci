"""Convert trigger status fields to enums

Revision ID: convert_trigger_enums
Revises: (fill in with previous revision)
Create Date: 2025-01-18 20:45:00.000000

"""

from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "convert_trigger_enums"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Convert trigger and trigger_event status fields from VARCHAR to ENUMs.

    Steps:
    1. Create the new enum types
    2. Update existing data to uppercase
    3. Alter columns to use enum type
    """

    # Create enum types
    trigger_status_enum = postgresql.ENUM(
        "ACTIVE", "PAUSED", "ERROR", "EXPIRED", name="triggerstatus"
    )
    trigger_status_enum.create(op.get_bind())

    trigger_event_status_enum = postgresql.ENUM(
        "PENDING", "DELIVERED", "FAILED", "EXPIRED", name="triggereventstatus"
    )
    trigger_event_status_enum.create(op.get_bind())

    # Update existing data to uppercase
    op.execute("UPDATE triggers SET status = UPPER(status)")
    op.execute("UPDATE trigger_events SET status = UPPER(status)")

    # Alter columns to use enum types
    # For triggers table
    op.execute("""
        ALTER TABLE triggers
        ALTER COLUMN status TYPE triggerstatus
        USING status::triggerstatus
    """)

    # For trigger_events table
    op.execute("""
        ALTER TABLE trigger_events
        ALTER COLUMN status TYPE triggereventstatus
        USING status::triggereventstatus
    """)


def downgrade() -> None:
    """
    Revert trigger and trigger_event status fields from ENUMs to VARCHAR.
    """

    # Alter columns back to VARCHAR
    op.execute("""
        ALTER TABLE triggers
        ALTER COLUMN status TYPE VARCHAR(255)
        USING status::text
    """)

    op.execute("""
        ALTER TABLE trigger_events
        ALTER COLUMN status TYPE VARCHAR(255)
        USING status::text
    """)

    # Update data back to lowercase
    op.execute("UPDATE triggers SET status = LOWER(status)")
    op.execute("UPDATE trigger_events SET status = LOWER(status)")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS triggerstatus")
    op.execute("DROP TYPE IF EXISTS triggereventstatus")
