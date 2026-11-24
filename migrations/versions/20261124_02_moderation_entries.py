"""Create normalized moderation entries and migrate legacy lists.

Revision ID: 20261124_02
Revises: 20261124_01
Create Date: 2026-11-24
"""

from alembic import op
import sqlalchemy as sa

revision = "20261124_02"
down_revision = "20261124_01"
branch_labels = None
depends_on = None


def _normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


def upgrade() -> None:
    op.create_table(
        "moderation_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.String(length=1000), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("kind", "normalized_value", name="uq_moderation_entry_kind_value"),
        sa.CheckConstraint("kind IN ('BLOCKED_TERM', 'INVALID_EXAMPLE')", name="ck_moderation_entry_kind"),
    )
    op.create_index("ix_moderation_entries_kind", "moderation_entries", ["kind"])
    op.create_index("ix_moderation_entries_is_active", "moderation_entries", ["is_active"])
    connection = op.get_bind()
    settings = connection.execute(
        sa.text("SELECT blocked_words, invalid_message_examples FROM general_settings WHERE id = 1")
    ).mappings().first()
    if settings is None:
        return
    rows = []
    for kind, raw in (("BLOCKED_TERM", settings["blocked_words"] or ""), ("INVALID_EXAMPLE", settings["invalid_message_examples"] or "")):
        seen = set()
        for line in raw.splitlines():
            value = " ".join(line.split()).strip()
            normalized = _normalize(value)
            if not value or normalized in seen:
                continue
            if len(normalized) > 1000:
                raise ValueError("Legacy moderation entry exceeds 1000 normalized characters.")
            seen.add(normalized)
            rows.append({"kind": kind, "value": value, "normalized_value": normalized})
    if rows:
        connection.execute(
            sa.text(
                "INSERT INTO moderation_entries (kind, value, normalized_value) "
                "VALUES (:kind, :value, :normalized_value)"
            ),
            rows,
        )
    connection.execute(
        sa.text("UPDATE general_settings SET blocked_words = '', invalid_message_examples = '' WHERE id = 1")
    )


def downgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT kind, value FROM moderation_entries WHERE is_active = TRUE ORDER BY id")
    ).mappings().all()
    blocked = [row["value"] for row in rows if row["kind"] == "BLOCKED_TERM"]
    examples = [row["value"] for row in rows if row["kind"] == "INVALID_EXAMPLE"]
    connection.execute(
        sa.text("UPDATE general_settings SET blocked_words = :blocked, invalid_message_examples = :examples WHERE id = 1"),
        {"blocked": "\\n".join(blocked), "examples": "\\n".join(examples)},
    )
    op.drop_index("ix_moderation_entries_is_active", table_name="moderation_entries")
    op.drop_index("ix_moderation_entries_kind", table_name="moderation_entries")
    op.drop_table("moderation_entries")
