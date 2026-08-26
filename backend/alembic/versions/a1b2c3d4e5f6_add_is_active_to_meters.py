"""add_is_active_to_meters

Adds the ``is_active`` flag to the ``meters`` table. Several read paths (insights
default-meter lookup, the AI assistant) select the user's active meter, but the column
was missing from the model, causing those queries to fail at runtime. Existing rows are
backfilled to active via the server default.

Revision ID: a1b2c3d4e5f6
Revises: e6f168c90ff8
Create Date: 2026-08-24 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'e6f168c90ff8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'meters',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column('meters', 'is_active')
