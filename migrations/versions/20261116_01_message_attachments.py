"""Add metadata for private message attachments.

Revision ID: 20261116_01
Revises: 20261110_01
Create Date: 2026-11-16
"""

from alembic import op
import sqlalchemy as sa

revision = "20261116_01"
down_revision = "20261114_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column("storage_key", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "attachments",
        sa.Column(
            "content_type",
            sa.String(length=120),
            nullable=False,
            server_default="application/octet-stream",
        ),
    )
    op.add_column(
        "attachments",
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "attachments",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_attachments_message_id", "attachments", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_attachments_message_id", table_name="attachments")
    op.drop_column("attachments", "created_at")
    op.drop_column("attachments", "size_bytes")
    op.drop_column("attachments", "content_type")
    op.drop_column("attachments", "storage_key")
