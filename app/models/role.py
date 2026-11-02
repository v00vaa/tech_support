"""Role and permission models for configurable RBAC."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Base, db

if TYPE_CHECKING:
    from app.models.employee import Employee


employee_roles = Table(
    "employee_roles",
    db.metadata,
    Column(
        "employee_id", Integer, ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True
    ),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permissions = Table(
    "role_permissions",
    db.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "permission_id",
        Integer,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Role(Base):
    """A named collection of permissions, optionally scoped to a main role."""

    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("scope_role_id", "role_type", name="uq_roles_scope_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    role_type: Mapped[str] = mapped_column(String(20), default="MAIN", nullable=False)
    scope_role_id: Mapped[int | None] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=True, index=True
    )

    scope_role: Mapped[Role | None] = relationship(
        remote_side="Role.id",
        back_populates="scoped_roles",
        foreign_keys=[scope_role_id],
    )
    scoped_roles: Mapped[list[Role]] = relationship(
        back_populates="scope_role",
        cascade="all, delete-orphan",
        foreign_keys=[scope_role_id],
    )
    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permissions, back_populates="roles", lazy="selectin"
    )
    employees: Mapped[list[Employee]] = relationship(
        secondary=employee_roles, back_populates="roles"
    )


class Permission(Base):
    """A single application capability."""

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(80), nullable=False)

    roles: Mapped[list[Role]] = relationship(
        secondary=role_permissions, back_populates="permissions"
    )
