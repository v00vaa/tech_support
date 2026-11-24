"""Audit record for rejected customer messages."""

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base


class ModerationEvent(Base):
    """Store rejected messages for authorized staff review."""

    __tablename__ = "moderation_events"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('ACCEPTED', 'REJECTED', 'BYPASSED')",
            name="ck_moderation_event_decision",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    dialog_id: Mapped[int | None] = mapped_column(
        ForeignKey("dialogs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False, default="REJECTED")
    category: Mapped[str | None] = mapped_column(String(80))
    matched_value: Mapped[str | None] = mapped_column(Text)
    match_type: Mapped[str | None] = mapped_column(String(20))
    model_name: Mapped[str | None] = mapped_column(String(120))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="NEW", index=True
    )
    reviewed_by_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
