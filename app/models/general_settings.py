"""Persistent global application settings."""

from sqlalchemy import CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base


class GeneralSettings(Base):
    """Singleton settings shared across the support application."""

    __tablename__ = "general_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_general_settings_singleton"),
        CheckConstraint(
            "closed_dialog_retention_days IS NULL OR closed_dialog_retention_days > 0",
            name="ck_general_settings_retention_positive",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    closed_dialog_retention_days: Mapped[int | None] = mapped_column(nullable=True, default=None)
    web_channel_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
