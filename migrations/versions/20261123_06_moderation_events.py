"""Add moderation decision journal.

Revision ID: 20261123_06
Revises: 20261123_05
Create Date: 2026-11-23
"""

from alembic import op
import sqlalchemy as sa

revision = "20261123_06"
down_revision = "20261123_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "moderation_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "dialog_id",
            sa.Integer(),
            sa.ForeignKey("dialogs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False, server_default="REJECTED"),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("review_status", sa.String(length=20), nullable=False, server_default="NEW"),
        sa.Column(
            "reviewed_by_employee_id",
            sa.Integer(),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
    )
    op.create_index("ix_moderation_events_client_id", "moderation_events", ["client_id"])
    op.create_index("ix_moderation_events_dialog_id", "moderation_events", ["dialog_id"])
    op.create_index("ix_moderation_events_review_status", "moderation_events", ["review_status"])


def downgrade() -> None:
    op.drop_index("ix_moderation_events_review_status", table_name="moderation_events")
    op.drop_index("ix_moderation_events_dialog_id", table_name="moderation_events")
    op.drop_index("ix_moderation_events_client_id", table_name="moderation_events")
    op.drop_table("moderation_events")
