"""Add scoped special role metadata.

Revision ID: 20261102_01
Revises: 20261030_02
Create Date: 2026-11-02
"""

from alembic import op
import sqlalchemy as sa

revision = "20261102_01"
down_revision = "20261030_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "roles",
        sa.Column("role_type", sa.String(length=20), nullable=False, server_default="MAIN"),
    )
    op.add_column("roles", sa.Column("scope_role_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_roles_scope_role_id_roles",
        "roles",
        "roles",
        ["scope_role_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_roles_scope_role_id", "roles", ["scope_role_id"])
    op.create_unique_constraint(
        "uq_roles_scope_type",
        "roles",
        ["scope_role_id", "role_type"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_roles_scope_type", "roles", type_="unique")
    op.drop_index("ix_roles_scope_role_id", table_name="roles")
    op.drop_constraint("fk_roles_scope_role_id_roles", "roles", type_="foreignkey")
    op.drop_column("roles", "scope_role_id")
    op.drop_column("roles", "role_type")
