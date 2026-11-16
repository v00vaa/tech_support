"""Add configurable first-line support role.

Revision ID: 20261116_02
Revises: 20261116_01
Create Date: 2026-11-16
"""

from alembic import op
import sqlalchemy as sa

revision = "20261116_02"
down_revision = "20261116_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "roles",
        sa.Column("is_first_line", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Preserve the previous default queue for installations that already have it.
    op.execute(
        sa.text(
            "UPDATE roles SET is_first_line = TRUE "
            "WHERE code = 'support_level_1' AND role_type = 'MAIN' AND is_active = TRUE"
        )
    )
    op.create_index(
        "uq_roles_single_first_line",
        "roles",
        ["is_first_line"],
        unique=True,
        postgresql_where=sa.text("is_first_line IS TRUE"),
        sqlite_where=sa.text("is_first_line = 1"),
    )


def downgrade() -> None:
    op.drop_index("uq_roles_single_first_line", table_name="roles")
    op.drop_column("roles", "is_first_line")
