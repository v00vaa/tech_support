"""Add configurable classifier confidence threshold.

Revision ID: 20261124_01
Revises: 20261123_06
Create Date: 2026-11-24
"""

from alembic import op
import sqlalchemy as sa

revision = "20261124_01"
down_revision = "20261123_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "general_settings",
        sa.Column(
            "classifier_min_confidence",
            sa.Float(),
            nullable=False,
            server_default="0.75",
        ),
    )
    op.create_check_constraint(
        "ck_general_settings_classifier_confidence_range",
        "general_settings",
        "classifier_min_confidence >= 0 AND classifier_min_confidence <= 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_general_settings_classifier_confidence_range",
        "general_settings",
        type_="check",
    )
    op.drop_column("general_settings", "classifier_min_confidence")
