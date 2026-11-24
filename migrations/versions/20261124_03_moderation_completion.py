"""Add moderation match strategies, event metadata and journal retention.

Revision ID: 20261124_03
Revises: 20261124_02
Create Date: 2026-11-24
"""

from alembic import op
import sqlalchemy as sa

revision = "20261124_03"
down_revision = "20261124_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "moderation_entries",
        sa.Column("match_type", sa.String(length=20), nullable=False, server_default="WHOLE_WORD"),
    )
    op.create_check_constraint(
        "ck_moderation_entry_match_type",
        "moderation_entries",
        "match_type IN ('WHOLE_WORD', 'SUBSTRING', 'EXACT')",
    )
    op.add_column("moderation_events", sa.Column("matched_value", sa.Text(), nullable=True))
    op.add_column("moderation_events", sa.Column("match_type", sa.String(length=20), nullable=True))
    op.add_column("moderation_events", sa.Column("model_name", sa.String(length=120), nullable=True))
    op.create_check_constraint(
        "ck_moderation_event_decision",
        "moderation_events",
        "decision IN ('ACCEPTED', 'REJECTED', 'BYPASSED')",
    )
    op.add_column(
        "general_settings",
        sa.Column("moderation_event_retention_days", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_general_settings_moderation_retention_positive",
        "general_settings",
        "moderation_event_retention_days IS NULL OR moderation_event_retention_days > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_general_settings_moderation_retention_positive",
        "general_settings",
        type_="check",
    )
    op.drop_column("general_settings", "moderation_event_retention_days")
    op.drop_constraint("ck_moderation_event_decision", "moderation_events", type_="check")
    op.drop_column("moderation_events", "model_name")
    op.drop_column("moderation_events", "match_type")
    op.drop_column("moderation_events", "matched_value")
    op.drop_constraint("ck_moderation_entry_match_type", "moderation_entries", type_="check")
    op.drop_column("moderation_entries", "match_type")
