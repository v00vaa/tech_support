"""Dialog operations and intentionally small status-transition policy."""

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import update
from sqlalchemy.engine import CursorResult

from app.extensions import db
from app.models.dialog import Dialog, DialogStatus
from app.models.message import AuthorType, Message
from app.services.attachment_storage_service import remove_attachment_files

ALLOWED_TRANSITIONS: dict[DialogStatus, set[DialogStatus]] = {
    DialogStatus.OPEN: {DialogStatus.IN_PROGRESS, DialogStatus.CLOSED},
    DialogStatus.IN_PROGRESS: {
        DialogStatus.WAITING_CLIENT,
        DialogStatus.WAITING_EMPLOYEE,
        DialogStatus.RESOLVED,
        DialogStatus.CLOSED,
    },
    DialogStatus.WAITING_CLIENT: {
        DialogStatus.IN_PROGRESS,
        DialogStatus.RESOLVED,
        DialogStatus.CLOSED,
    },
    DialogStatus.WAITING_EMPLOYEE: {DialogStatus.IN_PROGRESS, DialogStatus.CLOSED},
    DialogStatus.RESOLVED: {DialogStatus.CLOSED, DialogStatus.IN_PROGRESS},
    DialogStatus.CLOSED: {DialogStatus.OPEN, DialogStatus.IN_PROGRESS},
}


def create_dialog(client_id: int, employee_id: int | None, subject: str, channel: str) -> Dialog:
    dialog = Dialog(
        client_id=client_id, responsible_employee_id=employee_id, subject=subject, channel=channel
    )
    db.session.add(dialog)
    db.session.commit()
    return dialog


def update_dialog(
    dialog: Dialog, client_id: int, employee_id: int | None, subject: str, channel: str
) -> Dialog:
    dialog.client_id, dialog.responsible_employee_id = client_id, employee_id
    dialog.subject, dialog.channel = subject, channel
    db.session.commit()
    return dialog


def delete_dialog(dialog: Dialog) -> None:
    """Delete a dialog and its attachment files after the database commit succeeds."""
    storage_keys = [
        attachment.storage_key
        for message in dialog.messages
        for attachment in message.attachments
        if attachment.storage_key
    ]
    db.session.delete(dialog)
    db.session.commit()
    remove_attachment_files(storage_keys)


def assign_employee(dialog: Dialog, employee_id: int | None) -> Dialog:
    dialog.responsible_employee_id = employee_id
    if employee_id is None and dialog.assigned_role_id is not None:
        dialog.role_assigned_at = datetime.now(UTC)
    db.session.commit()
    return dialog


def claim_dialog(dialog_id: int, employee_id: int, role_ids: list[int]) -> bool:
    """Atomically claim a dialog from one of the employee's queues and record the event."""
    if not role_ids:
        return False

    result = cast(
        CursorResult[Any],
        db.session.execute(
            update(Dialog)
            .where(
                Dialog.id == dialog_id,
                Dialog.assigned_role_id.in_(role_ids),
                Dialog.responsible_employee_id.is_(None),
                Dialog.status.in_([DialogStatus.OPEN, DialogStatus.WAITING_EMPLOYEE]),
            )
            .values(
                responsible_employee_id=employee_id,
                status=DialogStatus.IN_PROGRESS,
                updated_at=datetime.now(UTC),
            )
        ),
    )
    if result.rowcount != 1:
        db.session.rollback()
        return False

    db.session.add(
        Message(
            dialog_id=dialog_id,
            author_type=AuthorType.SYSTEM,
            author_id=None,
            text="Обращение взял в работу сотрудник.",
            is_internal=False,
        )
    )
    db.session.commit()
    return True


def change_status(dialog: Dialog, status: DialogStatus) -> Dialog:
    if status != dialog.status and status not in ALLOWED_TRANSITIONS[dialog.status]:
        raise ValueError("Недопустимый переход статуса")
    if (
        dialog.status == DialogStatus.WAITING_CLIENT
        and status != DialogStatus.WAITING_CLIENT
        and dialog.assigned_role_id is not None
    ):
        dialog.role_assigned_at = datetime.now(UTC)
    dialog.status = status
    dialog.closed_at = datetime.now(UTC) if status == DialogStatus.CLOSED else None
    db.session.commit()
    return dialog
