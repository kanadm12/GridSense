"""Add immutable tariff revisions and archiveable identities.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "archived_at" not in {column["name"] for column in inspector.get_columns("tariffs")}:
        op.add_column(
            "tariffs", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)
        )

    if "tariff_revisions" not in inspect(bind).get_table_names():
        op.create_table(
            "tariff_revisions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tariff_id", sa.Integer(), nullable=False),
            sa.Column("revision_number", sa.Integer(), nullable=False),
            sa.Column("source_type", sa.String(length=32), nullable=False),
            sa.Column("source_plan_id", sa.String(length=120), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("effective_from", sa.Date(), nullable=True),
            sa.Column("effective_to", sa.Date(), nullable=True),
            sa.Column("tariff_type", sa.String(length=20), nullable=False),
            sa.Column("retailer_name", sa.String(length=100), nullable=True),
            sa.Column("flat_rate_cents_kwh", sa.Float(), nullable=True),
            sa.Column("peak_rate_cents_kwh", sa.Float(), nullable=True),
            sa.Column("off_peak_rate_cents_kwh", sa.Float(), nullable=True),
            sa.Column("shoulder_rate_cents_kwh", sa.Float(), nullable=True),
            sa.Column("feed_in_rate_cents_kwh", sa.Float(), nullable=True),
            sa.Column("periods", sa.JSON(), nullable=True),
            sa.Column("rates_include_gst", sa.Boolean(), nullable=False),
            sa.Column("demand_charge_dollars_kw", sa.Float(), nullable=True),
            sa.Column("daily_supply_charge_cents", sa.Float(), nullable=True),
            sa.Column("unsupported_components", sa.JSON(), nullable=False),
            sa.Column("is_illustrative", sa.Boolean(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["tariff_id"], ["tariffs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tariff_id",
                "revision_number",
                name="uq_tariff_revision_number",
            ),
        )
        op.create_index(
            "ix_tariff_revisions_tariff_id", "tariff_revisions", ["tariff_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "tariff_revisions" in inspect(bind).get_table_names():
        op.drop_index("ix_tariff_revisions_tariff_id", table_name="tariff_revisions")
        op.drop_table("tariff_revisions")
    if "archived_at" in {
        column["name"] for column in inspect(bind).get_columns("tariffs")
    }:
        op.drop_column("tariffs", "archived_at")
