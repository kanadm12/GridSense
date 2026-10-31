"""Make per-user NEM12 file submissions idempotent.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_nem12_upload_user_file_hash"


def upgrade() -> None:
    bind = op.get_bind()
    existing_indexes = {index["name"] for index in inspect(bind).get_indexes("nem12_uploads")}
    if INDEX_NAME in existing_indexes:
        return

    duplicate_groups = bind.execute(
        sa.text(
            "SELECT user_id, file_hash FROM nem12_uploads "
            "WHERE user_id IS NOT NULL AND file_hash IS NOT NULL "
            "GROUP BY user_id, file_hash HAVING COUNT(*) > 1"
        )
    ).all()
    for user_id, file_hash in duplicate_groups:
        upload_rows = bind.execute(
            sa.text(
                "SELECT id, status FROM nem12_uploads "
                "WHERE user_id = :user_id AND file_hash = :file_hash "
                "ORDER BY CASE WHEN status = 'completed' THEN 0 ELSE 1 END, id"
            ),
            {"user_id": user_id, "file_hash": file_hash},
        ).all()
        duplicate_ids = [row.id for row in upload_rows[1:]]
        if duplicate_ids:
            bind.execute(
                sa.text("UPDATE nem12_uploads SET file_hash = NULL WHERE id IN :ids").bindparams(
                    sa.bindparam("ids", expanding=True)
                ),
                {"ids": duplicate_ids},
            )

    op.create_index(
        INDEX_NAME,
        "nem12_uploads",
        ["user_id", "file_hash"],
        unique=True,
    )


def downgrade() -> None:
    existing_indexes = {
        index["name"] for index in inspect(op.get_bind()).get_indexes("nem12_uploads")
    }
    if INDEX_NAME in existing_indexes:
        op.drop_index(INDEX_NAME, table_name="nem12_uploads")
