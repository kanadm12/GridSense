"""Add source-unit, time-basis, and provenance fields to interval readings.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("readings")
    }
    columns = (
        sa.Column("source_value", sa.Float(), nullable=True),
        sa.Column("source_unit", sa.String(length=10), nullable=True),
        sa.Column("provenance_kind", sa.String(length=20), nullable=True),
        sa.Column("source_time_basis", sa.String(length=64), nullable=True),
    )
    for column in columns:
        if column.name not in existing_columns:
            op.add_column("readings", column)


def downgrade() -> None:
    bind = op.get_bind()
    existing_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("readings")
    }
    for column_name in (
        "source_time_basis",
        "provenance_kind",
        "source_unit",
        "source_value",
    ):
        if column_name in existing_columns:
            op.drop_column("readings", column_name)
