"""Create OAuth1 temp tokens table

Revision ID: f1a2b3c4d5e6
Revises: add_perf_indexes
Create Date: 2025-01-15 10:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'add_perf_indexes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create OAuth1 temp tokens table for storing request tokens during OAuth1 flow
    op.create_table(
        'oauth1_temp_tokens',
        sa.Column('oauth_token', sa.String(length=255), nullable=False, primary_key=True),
        sa.Column('state_jwt', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    )
    # Add index on expires_at for efficient cleanup queries
    op.create_index('ix_oauth1_temp_tokens_expires_at', 'oauth1_temp_tokens', ['expires_at'])


def downgrade() -> None:
    op.drop_index('ix_oauth1_temp_tokens_expires_at', table_name='oauth1_temp_tokens')
    op.drop_table('oauth1_temp_tokens')
