"""Support dialog model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from app.extensions import db


class DialogStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_CLIENT = "WAITING_CLIENT"
    WAITING_EMPLOYEE = "WAITING_EMPLOYEE"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class Dialog(db.Model):  # type: ignore[name-defined]
    __tablename__ = "dialogs"

    id: db.Mapped[int] = db.mapped_column(primary_key=True)
    client_id: db.Mapped[int] = db.mapped_column(db.ForeignKey("clients.id"), nullable=False, index=True)
    responsible_employee_id: db.Mapped[int | None] = db.mapped_column(db.ForeignKey("employees.id"), index=True)
    subject: db.Mapped[str] = db.mapped_column(db.String(255), nullable=False)
    status: db.Mapped[DialogStatus] = db.mapped_column(db.Enum(DialogStatus), default=DialogStatus.OPEN, nullable=False)
    channel: db.Mapped[str] = db.mapped_column(db.String(50), default="Web", nullable=False)
    created_at: db.Mapped[datetime] = db.mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: db.Mapped[datetime] = db.mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    closed_at: db.Mapped[datetime | None] = db.mapped_column()
    client: db.Mapped["Client"] = db.relationship(back_populates="dialogs")
    responsible_employee: db.Mapped["Employee | None"] = db.relationship(back_populates="assigned_dialogs")
    messages: db.Mapped[list["Message"]] = db.relationship(back_populates="dialog", cascade="all, delete-orphan", order_by="Message.created_at")
