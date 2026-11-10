"""Add role-to-role dialog routing and queue assignment metadata.

Revision ID: 20261110_01
Revises: 20261102_01
Create Date: 2026-11-10
"""

from alembic import op
import sqlalchemy as sa

revision = "20261110_01"
down_revision = "20261102_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "role_routes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_role_id", sa.Integer(), nullable=False),
        sa.Column("target_role_id", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("auto_forward_after_minutes", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "source_role_id != target_role_id",
            name="ck_role_routes_distinct_roles",
        ),
        sa.CheckConstraint(
            "auto_forward_after_minutes IS NULL OR auto_forward_after_minutes > 0",
            name="ck_role_routes_positive_timeout",
        ),
        sa.ForeignKeyConstraint(["source_role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_role_id",
            "target_role_id",
            name="uq_role_routes_source_target",
        ),
    )
    op.create_index("ix_role_routes_source_role_id", "role_routes", ["source_role_id"])
    op.create_index("ix_role_routes_target_role_id", "role_routes", ["target_role_id"])
    op.create_index(
        "uq_role_routes_one_default_per_source",
        "role_routes",
        ["source_role_id"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
        sqlite_where=sa.text("is_default = 1"),
    )
    op.add_column("dialogs", sa.Column("assigned_role_id", sa.Integer(), nullable=True))
    op.add_column(
        "dialogs",
        sa.Column("role_assigned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_dialogs_assigned_role_id_roles",
        "dialogs",
        "roles",
        ["assigned_role_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_dialogs_assigned_role_id", "dialogs", ["assigned_role_id"])


def downgrade() -> None:
    op.drop_index("ix_dialogs_assigned_role_id", table_name="dialogs")
    op.drop_constraint("fk_dialogs_assigned_role_id_roles", "dialogs", type_="foreignkey")
    op.drop_column("dialogs", "role_assigned_at")
    op.drop_column("dialogs", "assigned_role_id")
    op.drop_index("uq_role_routes_one_default_per_source", table_name="role_routes")
    op.drop_index("ix_role_routes_target_role_id", table_name="role_routes")
    op.drop_index("ix_role_routes_source_role_id", table_name="role_routes")
    op.drop_table("role_routes")
