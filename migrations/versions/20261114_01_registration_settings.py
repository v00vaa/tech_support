"""Add customer login and registration options.

Revision ID: 20261114_01
Revises: 20261111_01
Create Date: 2026-11-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20261114_01"
down_revision = "20261111_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("login", sa.String(length=80), nullable=True))
    op.create_index("ix_clients_login", "clients", ["login"], unique=True)
    op.alter_column("clients", "email", existing_type=sa.String(length=255), nullable=True)

    op.create_table(
        "registration_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("automatic_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("manual_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("phone_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "collect_request_details",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.CheckConstraint("id = 1", name="ck_registration_settings_singleton"),
    )
    op.execute(
        """
        INSERT INTO registration_settings
            (id, automatic_enabled, manual_enabled, email_enabled, phone_enabled,
             collect_request_details)
        VALUES (1, TRUE, TRUE, TRUE, FALSE, FALSE)
        """
    )


def downgrade() -> None:
    op.drop_table("registration_settings")
    op.alter_column("clients", "email", existing_type=sa.String(length=255), nullable=False)
    op.drop_index("ix_clients_login", table_name="clients")
    op.drop_column("clients", "login")
