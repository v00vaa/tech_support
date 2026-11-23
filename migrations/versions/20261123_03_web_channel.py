"""Add enablement setting for the Web intake channel.

Revision ID: 20261123_03
Revises: 20261123_02
Create Date: 2026-11-23
"""

from alembic import op
import sqlalchemy as sa

revision = "20261123_03"
down_revision = "20261123_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "general_settings",
        sa.Column("web_channel_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("general_settings", "web_channel_enabled")
