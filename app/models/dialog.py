"""Support dialog model."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Base, db

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.employee import Employee
    from app.models.message import Message
    from app.models.role import Role


class DialogStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_CLIENT = "WAITING_CLIENT"
    WAITING_EMPLOYEE = "WAITING_EMPLOYEE"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class Dialog(Base):
    __tablename__ = "dialogs"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    responsible_employee_id: Mapped[int | None] = mapped_column(
        db.ForeignKey("employees.id"), index=True
    )
    assigned_role_id: Mapped[int | None] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL"), index=True
    )
    role_assigned_at: Mapped[datetime | None] = mapped_column()
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[DialogStatus] = mapped_column(
        db.Enum(DialogStatus), default=DialogStatus.OPEN, nullable=False
    )
    channel: Mapped[str] = mapped_column(String(50), default="Web", nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column()
    client: Mapped[Client] = relationship(back_populates="dialogs")
    responsible_employee: Mapped[Employee | None] = relationship(back_populates="assigned_dialogs")
    assigned_role: Mapped[Role | None] = relationship(back_populates="assigned_dialogs")
    messages: Mapped[list[Message]] = relationship(
        back_populates="dialog", cascade="all, delete-orphan", order_by="Message.created_at"
    )
