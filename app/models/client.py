"""Client persistence model."""

from __future__ import annotations

from app.extensions import db


class Client(db.Model):  # type: ignore[name-defined]
    __tablename__ = "clients"

    id: db.Mapped[int] = db.mapped_column(primary_key=True)
    name: db.Mapped[str] = db.mapped_column(db.String(120), nullable=False)
    email: db.Mapped[str] = db.mapped_column(db.String(255), unique=True, nullable=False, index=True)
    phone: db.Mapped[str | None] = db.mapped_column(db.String(40))
    dialogs: db.Mapped[list["Dialog"]] = db.relationship(back_populates="client", cascade="all, delete-orphan")
