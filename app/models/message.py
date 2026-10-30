"""Message model with soft deletion."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from app.extensions import db


class AuthorType(StrEnum):
    CLIENT = "CLIENT"
    EMPLOYEE = "EMPLOYEE"
    SYSTEM = "SYSTEM"


class Message(db.Model):  # type: ignore[name-defined]
    __tablename__ = "messages"

    id: db.Mapped[int] = db.mapped_column(primary_key=True)
    dialog_id: db.Mapped[int] = db.mapped_column(db.ForeignKey("dialogs.id"), nullable=False, index=True)
    author_type: db.Mapped[AuthorType] = db.mapped_column(db.Enum(AuthorType), nullable=False)
    author_id: db.Mapped[int | None] = db.mapped_column()
    text: db.Mapped[str] = db.mapped_column(db.Text, nullable=False)
    created_at: db.Mapped[datetime] = db.mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: db.Mapped[datetime] = db.mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at: db.Mapped[datetime | None] = db.mapped_column()
    dialog: db.Mapped["Dialog"] = db.relationship(back_populates="messages")
