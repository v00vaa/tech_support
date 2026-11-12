"""Add local customer credentials and external identity.

Revision ID: 20261112_01
Revises: 20261111_01
Create Date: 2026-11-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20261112_01"
down_revision = "20261111_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column("clients", sa.Column("external_id", sa.String(length=128), nullable=True))
    op.create_unique_constraint("uq_clients_external_id", "clients", ["external_id"])


def downgrade() -> None:
    op.drop_constraint("uq_clients_external_id", "clients", type_="unique")
    op.drop_column("clients", "external_id")
    op.drop_column("clients", "password_hash")
