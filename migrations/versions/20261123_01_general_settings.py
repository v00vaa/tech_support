"""Add global settings for closed-dialog retention.

Revision ID: 20261123_01
Revises: 20261116_02
Create Date: 2026-11-23
"""

from alembic import op
import sqlalchemy as sa

revision = "20261123_01"
down_revision = "20261116_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "general_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("closed_dialog_retention_days", sa.Integer(), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_general_settings_singleton"),
        sa.CheckConstraint(
            "closed_dialog_retention_days IS NULL OR closed_dialog_retention_days > 0",
            name="ck_general_settings_retention_positive",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("general_settings")
