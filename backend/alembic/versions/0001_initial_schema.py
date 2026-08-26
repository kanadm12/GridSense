"""Create the initial GridSense schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-18
"""

from alembic import op

from app.models import Base

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all tables represented by the initial model metadata."""
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    """Remove the initial GridSense schema."""
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
