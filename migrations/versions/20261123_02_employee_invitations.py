"""Create single-use employee invitations.

Revision ID: 20261123_02
Revises: 20261123_01
Create Date: 2026-11-23
"""

from alembic import op
import sqlalchemy as sa

revision = "20261123_02"
down_revision = "20261123_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employee_invitations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("position", sa.String(length=120), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("invited_by_employee_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_employee_invitations_role_id_roles",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_employee_id"],
            ["employees.id"],
            name="fk_employee_invitations_invited_by_employee_id_employees",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_employee_invitations_token_hash"),
    )
    op.create_index(
        "ix_employee_invitations_email",
        "employee_invitations",
        ["email"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_employee_invitations_email", table_name="employee_invitations")
    op.drop_table("employee_invitations")
