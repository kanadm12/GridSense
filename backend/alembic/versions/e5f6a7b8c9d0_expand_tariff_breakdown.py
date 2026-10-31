"""Store effective-dated tariff and bill-calculation inputs.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("tariffs")}
    additions = (
        ("feed_in_rate_cents_kwh", sa.Float(), True, None),
        ("periods", sa.JSON(), True, None),
        ("effective_from", sa.Date(), True, None),
        ("effective_to", sa.Date(), True, None),
        ("rates_include_gst", sa.Boolean(), False, True),
        ("is_preset", sa.Boolean(), False, False),
    )
    for name, column_type, nullable, default in additions:
        if name not in columns:
            op.add_column(
                "tariffs",
                sa.Column(
                    name,
                    column_type,
                    nullable=nullable,
                    server_default=sa.true() if default is True else (
                        sa.false() if default is False else None
                    ),
                ),
            )


def downgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("tariffs")}
    for name in (
        "is_preset",
        "rates_include_gst",
        "effective_to",
        "effective_from",
        "periods",
        "feed_in_rate_cents_kwh",
    ):
        if name in columns:
            op.drop_column("tariffs", name)
