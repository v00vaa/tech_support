"""Attachment placeholder; binary storage is intentionally deferred."""

from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class Attachment(db.Model):  
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"))
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
