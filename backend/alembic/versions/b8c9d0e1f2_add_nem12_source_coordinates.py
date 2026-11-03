"""Retain NEM12 channel identifiers and source interval coordinates.

Revision ID: b8c9d0e1f2
Revises: a7b8c9d0e1f2
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_missing_columns(table_name: str, columns: tuple[sa.Column, ...]) -> None:
    bind = op.get_bind()
    existing_columns = {
        column["name"] for column in sa.inspect(bind).get_columns(table_name)
    }
    for column in columns:
        if column.name not in existing_columns:
            op.add_column(table_name, column)


def _drop_existing_columns(table_name: str, column_names: tuple[str, ...]) -> None:
    bind = op.get_bind()
    existing_columns = {
        column["name"] for column in sa.inspect(bind).get_columns(table_name)
    }
    for column_name in column_names:
        if column_name in existing_columns:
            op.drop_column(table_name, column_name)


def upgrade() -> None:
    _add_missing_columns(
        "meters",
        (sa.Column("mdm_data_stream_identifier", sa.String(length=2), nullable=True),),
    )
    _add_missing_columns(
        "readings",
        (
            sa.Column("source_interval_date", sa.Date(), nullable=True),
            sa.Column("source_interval_number", sa.Integer(), nullable=True),
            sa.Column("source_nmi_configuration", sa.String(length=240), nullable=True),
            sa.Column("source_record_quality_method", sa.String(length=3), nullable=True),
        ),
    )


def downgrade() -> None:
    _drop_existing_columns(
        "readings",
        (
            "source_record_quality_method",
            "source_nmi_configuration",
            "source_interval_number",
            "source_interval_date",
        ),
    )
    _drop_existing_columns("meters", ("mdm_data_stream_identifier",))
