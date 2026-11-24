"""Normalized entries used by deterministic moderation and classifier examples."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base


class ModerationEntry(Base):
    """One managed blocked term or classifier example."""

    __tablename__ = "moderation_entries"
    __table_args__ = (
        UniqueConstraint("kind", "normalized_value", name="uq_moderation_entry_kind_value"),
        CheckConstraint(
            "kind IN ('BLOCKED_TERM', 'INVALID_EXAMPLE')",
            name="ck_moderation_entry_kind",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(1000), nullable=False)
    category: Mapped[str | None] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
