"""Client persistence model."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.dialog import Dialog

class Client(db.Model):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    dialogs: Mapped[list["Dialog"]] = relationship(back_populates="client", cascade="all, delete-orphan")
