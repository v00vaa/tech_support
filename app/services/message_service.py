"""Message operations, including internal notes and soft deletion."""

from datetime import datetime, timezone

from app.extensions import db
from app.models.message import AuthorType, Message


def create_message(
    dialog_id: int,
    author_type: AuthorType,
    author_id: int | None,
    text: str,
    *,
    is_internal: bool = False,
) -> Message:
    message = Message(
        dialog_id=dialog_id,
        author_type=author_type,
        author_id=author_id,
        text=text,
        is_internal=is_internal,
    )
    db.session.add(message)
    db.session.commit()
    return message


def update_message(message: Message, text: str) -> Message:
    message.text = text
    db.session.commit()
    return message


def delete_message(message: Message) -> None:
    message.deleted_at = datetime.now(timezone.utc)
    db.session.commit()
