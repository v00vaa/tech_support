"""Add an active flag to customer accounts.

Revision ID: 20261114_02
Revises: 20261114_01
Create Date: 2026-11-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20261114_02"
down_revision = "20261114_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("clients", "is_active")
