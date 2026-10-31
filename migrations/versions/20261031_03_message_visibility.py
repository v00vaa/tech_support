"""Add internal visibility flag to messages.

Revision ID: 20261031_03
Revises: 20261030_02
Create Date: 2026-10-31
"""

from alembic import op
import sqlalchemy as sa

revision = "20261031_03"
down_revision = "20261030_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("messages", "is_internal")
