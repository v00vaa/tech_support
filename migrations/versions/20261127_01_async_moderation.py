"""Add persisted moderation state to customer messages.

Revision ID: 20261127_01
Revises: 20261124_04
Create Date: 2026-11-27
"""

from alembic import op
import sqlalchemy as sa

revision = "20261127_01"
down_revision = "20261124_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "moderation_status",
            sa.String(length=20),
            nullable=False,
            server_default="ACCEPTED",
        ),
    )
    op.add_column(
        "messages",
        sa.Column("moderation_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("moderation_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_messages_moderation_status",
        "messages",
        "moderation_status IN "
        "('PENDING', 'PROCESSING', 'ACCEPTED', 'REJECTED', 'BYPASSED', 'SUPERSEDED')",
    )
    op.create_index(
        "ix_messages_moderation_queue",
        "messages",
        ["moderation_status", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_messages_moderation_queue", table_name="messages")
    op.drop_constraint("ck_messages_moderation_status", "messages", type_="check")
    op.drop_column("messages", "moderation_started_at")
    op.drop_column("messages", "moderation_reason")
    op.drop_column("messages", "moderation_status")
