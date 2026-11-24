"""Link moderation audit records to accepted message records.

Revision ID: 20261124_04
Revises: 20261124_03
Create Date: 2026-11-24
"""

from alembic import op
import sqlalchemy as sa

revision = "20261124_04"
down_revision = "20261124_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "moderation_events",
        sa.Column("message_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_moderation_events_message_id_messages",
        "moderation_events",
        "messages",
        ["message_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_moderation_events_message_id",
        "moderation_events",
        ["message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_moderation_events_message_id", table_name="moderation_events")
    op.drop_constraint(
        "fk_moderation_events_message_id_messages",
        "moderation_events",
        type_="foreignkey",
    )
    op.drop_column("moderation_events", "message_id")
