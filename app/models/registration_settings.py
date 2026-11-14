"""Persistent registration settings for customer accounts."""

from sqlalchemy import Boolean, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base


class RegistrationSettings(Base):
    """Singleton configuration controlling available customer registration options."""

    __tablename__ = "registration_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_registration_settings_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    automatic_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    manual_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    phone_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    collect_request_details: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
