"""Employee model and Flask-Login identity."""

from __future__ import annotations

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models.role import employee_roles


class Employee(UserMixin, db.Model):  # type: ignore[name-defined]
    __tablename__ = "employees"

    id: db.Mapped[int] = db.mapped_column(primary_key=True)
    name: db.Mapped[str] = db.mapped_column(db.String(120), nullable=False)
    email: db.Mapped[str] = db.mapped_column(db.String(255), unique=True, nullable=False, index=True)
    position: db.Mapped[str] = db.mapped_column(db.String(120), nullable=False, default="Специалист поддержки")
    password_hash: db.Mapped[str] = db.mapped_column(db.String(255), nullable=False)
    is_active: db.Mapped[bool] = db.mapped_column(default=True, nullable=False)
    must_change_password: db.Mapped[bool] = db.mapped_column(default=False, nullable=False)
    roles: db.Mapped[list["Role"]] = db.relationship(
        secondary=employee_roles, back_populates="employees", lazy="selectin"
    )
    assigned_dialogs: db.Mapped[list["Dialog"]] = db.relationship(back_populates="responsible_employee")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)
