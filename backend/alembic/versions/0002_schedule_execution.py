"""Track device schedule execution.

Revision ID: 0002_schedule_execution
Revises: 0001_initial_schema
Create Date: 2026-08-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_schedule_execution"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("device_schedules", sa.Column("last_executed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("device_schedules", "last_executed_at")
