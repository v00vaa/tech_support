"""Role and permission models for configurable RBAC."""

from __future__ import annotations

from app.extensions import db

employee_roles = db.Table(
    "employee_roles",
    db.Column("employee_id", db.Integer, db.ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True),
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permissions = db.Table(
    "role_permissions",
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    db.Column("permission_id", db.Integer, db.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class Role(db.Model):  # type: ignore[name-defined]
    """A named collection of permissions assignable to employees."""

    __tablename__ = "roles"

    id: db.Mapped[int] = db.mapped_column(primary_key=True)
    code: db.Mapped[str] = db.mapped_column(db.String(80), unique=True, nullable=False, index=True)
    name: db.Mapped[str] = db.mapped_column(db.String(120), nullable=False)
    description: db.Mapped[str | None] = db.mapped_column(db.String(500))
    is_system: db.Mapped[bool] = db.mapped_column(db.Boolean, default=False, nullable=False)
    is_active: db.Mapped[bool] = db.mapped_column(db.Boolean, default=True, nullable=False)
    permissions: db.Mapped[list["Permission"]] = db.relationship(
        secondary=role_permissions, back_populates="roles", lazy="selectin"
    )
    employees: db.Mapped[list["Employee"]] = db.relationship(
        secondary=employee_roles, back_populates="roles"
    )


class Permission(db.Model):  # type: ignore[name-defined]
    """A single application capability."""

    __tablename__ = "permissions"

    id: db.Mapped[int] = db.mapped_column(primary_key=True)
    code: db.Mapped[str] = db.mapped_column(db.String(120), unique=True, nullable=False, index=True)
    name: db.Mapped[str] = db.mapped_column(db.String(160), nullable=False)
    description: db.Mapped[str | None] = db.mapped_column(db.String(500))
    category: db.Mapped[str] = db.mapped_column(db.String(80), nullable=False)
    roles: db.Mapped[list[Role]] = db.relationship(
        secondary=role_permissions, back_populates="permissions"
    )
