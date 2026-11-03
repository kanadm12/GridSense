"""Add auditable weather-provider fetch and forecast records.

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(inspect(bind).get_table_names())
    if "external_fetch_runs" not in existing_tables:
        op.create_table(
            "external_fetch_runs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("provider", sa.String(length=40), nullable=False),
            sa.Column("source_version", sa.String(length=80), nullable=False),
            sa.Column("location_key", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_code", sa.String(length=40), nullable=True),
            sa.Column("provider_metadata", sa.JSON(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_external_fetch_provider_location_status",
            "external_fetch_runs",
            ["provider", "location_key", "status", "completed_at"],
        )
    if "weather_forecast_values" not in existing_tables:
        op.create_table(
            "weather_forecast_values",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("fetch_run_id", sa.String(length=36), nullable=False),
            sa.Column("source_time_label", sa.String(length=40), nullable=False),
            sa.Column("target_time_utc", sa.DateTime(timezone=True), nullable=False),
            sa.Column("interval_start_utc", sa.DateTime(timezone=True), nullable=True),
            sa.Column("interval_end_utc", sa.DateTime(timezone=True), nullable=True),
            sa.Column("time_semantics", sa.String(length=40), nullable=False),
            sa.Column("temperature_2m_c", sa.Float(), nullable=True),
            sa.Column("apparent_temperature_c", sa.Float(), nullable=True),
            sa.Column("relative_humidity_2m_percent", sa.Float(), nullable=True),
            sa.Column("cloud_cover_percent", sa.Float(), nullable=True),
            sa.Column("shortwave_radiation_w_m2", sa.Float(), nullable=True),
            sa.Column("source_units", sa.JSON(), nullable=False),
            sa.Column("normalized_units", sa.JSON(), nullable=False),
            sa.ForeignKeyConstraint(
                ["fetch_run_id"], ["external_fetch_runs.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "fetch_run_id", "target_time_utc", name="uq_weather_forecast_run_target"
            ),
        )
        op.create_index(
            "ix_weather_forecast_target_time",
            "weather_forecast_values",
            ["target_time_utc"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(inspect(bind).get_table_names())
    if "weather_forecast_values" in existing_tables:
        op.drop_index("ix_weather_forecast_target_time", table_name="weather_forecast_values")
        op.drop_table("weather_forecast_values")
    if "external_fetch_runs" in existing_tables:
        op.drop_index(
            "ix_external_fetch_provider_location_status", table_name="external_fetch_runs"
        )
        op.drop_table("external_fetch_runs")
