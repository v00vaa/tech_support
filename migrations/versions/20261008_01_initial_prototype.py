"""Initial support prototype tables.

Revision ID: 20261008_01
Revises:
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa

revision = "20261008_01"
down_revision = None
branch_labels = None
depends_on = None

dialog_status = sa.Enum("OPEN", "IN_PROGRESS", "WAITING_CLIENT", "WAITING_EMPLOYEE", "RESOLVED", "CLOSED", name="dialogstatus")
author_type = sa.Enum("CLIENT", "EMPLOYEE", "SYSTEM", name="authortype")


def upgrade() -> None:
    bind = op.get_bind()
    dialog_status.create(bind, checkfirst=True)
    author_type.create(bind, checkfirst=True)
    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=40)),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_clients_email", "clients", ["email"])
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("position", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_employees_email", "employees", ["email"])
    op.create_table(
        "dialogs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("responsible_employee_id", sa.Integer(), sa.ForeignKey("employees.id")),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("status", dialog_status, nullable=False),
        sa.Column("channel", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime()),
    )
    op.create_index("ix_dialogs_client_id", "dialogs", ["client_id"])
    op.create_index("ix_dialogs_responsible_employee_id", "dialogs", ["responsible_employee_id"])
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dialog_id", sa.Integer(), sa.ForeignKey("dialogs.id"), nullable=False),
        sa.Column("author_type", author_type, nullable=False),
        sa.Column("author_id", sa.Integer()),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime()),
    )
    op.create_index("ix_messages_dialog_id", "messages", ["dialog_id"])
    op.create_table(
        "attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id")),
        sa.Column("filename", sa.String(length=255), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("attachments")
    op.drop_index("ix_messages_dialog_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_dialogs_responsible_employee_id", table_name="dialogs")
    op.drop_index("ix_dialogs_client_id", table_name="dialogs")
    op.drop_table("dialogs")
    op.drop_index("ix_employees_email", table_name="employees")
    op.drop_table("employees")
    op.drop_index("ix_clients_email", table_name="clients")
    op.drop_table("clients")
    bind = op.get_bind()
    author_type.drop(bind, checkfirst=True)
    dialog_status.drop(bind, checkfirst=True)
