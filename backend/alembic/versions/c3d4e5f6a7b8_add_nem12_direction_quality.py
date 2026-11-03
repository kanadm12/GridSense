"""Preserve NEM12 channel direction and quality metadata.

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    meter_columns = {column["name"] for column in inspector.get_columns("meters")}
    reading_columns = {column["name"] for column in inspector.get_columns("readings")}

    if "register_id" not in meter_columns:
        op.add_column("meters", sa.Column("register_id", sa.String(length=10), nullable=True))
    if "direction" not in reading_columns:
        op.add_column("readings", sa.Column("direction", sa.String(length=10), nullable=True))
    if "quality_method" not in reading_columns:
        op.add_column("readings", sa.Column("quality_method", sa.String(length=3), nullable=True))
    if "reason_code" not in reading_columns:
        op.add_column("readings", sa.Column("reason_code", sa.String(length=3), nullable=True))
    if "reason_description" not in reading_columns:
        op.add_column("readings", sa.Column("reason_description", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    reading_columns = {column["name"] for column in inspector.get_columns("readings")}
    meter_columns = {column["name"] for column in inspector.get_columns("meters")}

    for column in ("reason_description", "reason_code", "quality_method", "direction"):
        if column in reading_columns:
            op.drop_column("readings", column)
    if "register_id" in meter_columns:
        op.drop_column("meters", "register_id")
