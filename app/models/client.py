"""Client persistence model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import Base

if TYPE_CHECKING:
    from app.models.dialog import Dialog


class Client(Base):
    """Customer profile and local Support Desk credentials."""

    __tablename__ = "clients"
    __table_args__ = (UniqueConstraint("external_id", name="uq_clients_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    login: Mapped[str | None] = mapped_column(String(80), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    # Nullable to keep existing manually-created prototype records compatible.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    # External identity is supplied by the main-system registration link.
    external_id: Mapped[str | None] = mapped_column(String(128))

    dialogs: Mapped[list[Dialog]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )

    def set_password(self, password: str) -> None:
        """Store a password hash; never persist the raw password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Check a password for a registered customer account."""
        return bool(self.password_hash and check_password_hash(self.password_hash, password))
