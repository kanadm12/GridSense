"""Persist interval length for explicit time-boundary calculations.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("readings")}
    if "interval_minutes" not in columns:
        op.add_column(
            "readings",
            sa.Column("interval_minutes", sa.Integer(), server_default="30", nullable=False),
        )


def downgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("readings")}
    if "interval_minutes" in columns:
        op.drop_column("readings", "interval_minutes")
