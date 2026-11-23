"""Add feature switches for moderation and Ollama.

Revision ID: 20261123_05
Revises: 20261123_04
Create Date: 2026-11-23
"""

from alembic import op
import sqlalchemy as sa

revision = "20261123_05"
down_revision = "20261123_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "general_settings",
        sa.Column(
            "blocked_words_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "general_settings",
        sa.Column(
            "classifier_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "general_settings",
        sa.Column(
            "ollama_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("general_settings", "ollama_enabled")
    op.drop_column("general_settings", "classifier_enabled")
    op.drop_column("general_settings", "blocked_words_enabled")
