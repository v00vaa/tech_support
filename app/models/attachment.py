"""Attachment placeholder; binary storage is intentionally deferred."""

from app.extensions import db


class Attachment(db.Model):  # type: ignore[name-defined]
    __tablename__ = "attachments"

    id: db.Mapped[int] = db.mapped_column(primary_key=True)
    message_id: db.Mapped[int | None] = db.mapped_column(db.ForeignKey("messages.id"))
    filename: db.Mapped[str] = db.mapped_column(db.String(255), nullable=False)
