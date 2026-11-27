"""Add configurable customer-facing AI assistant.

Revision ID: 20261127_02
Revises: 20261127_01
Create Date: 2026-11-27
"""

from alembic import op
import sqlalchemy as sa

revision = "20261127_02"
down_revision = "20261127_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "general_settings",
        sa.Column(
            "ai_assistant_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "general_settings",
        sa.Column(
            "ai_assistant_context",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "general_settings",
        sa.Column(
            "ai_assistant_prompt",
            sa.Text(),
            nullable=False,
            server_default=(
                "Ты — помощник первой линии технической поддержки. Помогай клиенту "
                "понять возможную причину проблемы, выполнить безопасные действия и "
                "предоставить недостающие сведения."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("general_settings", "ai_assistant_prompt")
    op.drop_column("general_settings", "ai_assistant_context")
    op.drop_column("general_settings", "ai_assistant_enabled")
