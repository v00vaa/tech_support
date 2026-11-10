"""Role-to-role dialog routing configuration."""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Base
from app.models.role import Role


class RoleRoute(Base):
    """An allowed outgoing route from one main role to another."""

    __tablename__ = "role_routes"
    __table_args__ = (
        UniqueConstraint("source_role_id", "target_role_id", name="uq_role_routes_source_target"),
        Index(
            "uq_role_routes_one_default_per_source",
            "source_role_id",
            unique=True,
            postgresql_where=text("is_default = true"),
            sqlite_where=text("is_default = 1"),
        ),
        CheckConstraint("source_role_id != target_role_id", name="ck_role_routes_distinct_roles"),
        CheckConstraint(
            "auto_forward_after_minutes IS NULL OR auto_forward_after_minutes > 0",
            name="ck_role_routes_positive_timeout",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_forward_after_minutes: Mapped[int | None] = mapped_column(Integer)

    source_role: Mapped[Role] = relationship(
        back_populates="outgoing_routes", foreign_keys=[source_role_id]
    )
    target_role: Mapped[Role] = relationship(
        back_populates="incoming_routes", foreign_keys=[target_role_id]
    )

