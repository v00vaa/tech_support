"""Message model with soft deletion."""

from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from datetime import datetime, timezone
from enum import StrEnum

from app.extensions import db

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.dialog import Dialog

class AuthorType(StrEnum):
    CLIENT = "CLIENT"
    EMPLOYEE = "EMPLOYEE"
    SYSTEM = "SYSTEM"


class Message(db.Model):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    dialog_id: Mapped[int] = mapped_column(ForeignKey("dialogs.id"), nullable=False, index=True)
    author_type: Mapped[AuthorType] = mapped_column(db.Enum(AuthorType), nullable=False)
    author_id: Mapped[int | None] = mapped_column()
    text: Mapped[str] = mapped_column(db.Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column()
    dialog: Mapped["Dialog"] = relationship(back_populates="messages")
