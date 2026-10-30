"""Employee model and Flask-Login identity."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models.role import employee_roles

if TYPE_CHECKING:
    from app.models.dialog import Dialog
    from app.models.role import Role


class Employee(db.Model):
    """Employee account used for authentication and support operations."""

    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    position: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="Специалист поддержки",
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    roles: Mapped[list[Role]] = relationship(
        secondary=employee_roles,
        back_populates="employees",
        lazy="selectin",
    )

    assigned_dialogs: Mapped[list[Dialog]] = relationship(
        back_populates="responsible_employee",
    )

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)