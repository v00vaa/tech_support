"""Dialog operations and intentionally small status-transition policy."""

from datetime import datetime, timezone

from app.extensions import db
from app.models.dialog import Dialog, DialogStatus

ALLOWED_TRANSITIONS: dict[DialogStatus, set[DialogStatus]] = {
    DialogStatus.OPEN: {DialogStatus.IN_PROGRESS, DialogStatus.CLOSED},
    DialogStatus.IN_PROGRESS: {DialogStatus.WAITING_CLIENT, DialogStatus.WAITING_EMPLOYEE, DialogStatus.RESOLVED, DialogStatus.CLOSED},
    DialogStatus.WAITING_CLIENT: {DialogStatus.IN_PROGRESS, DialogStatus.RESOLVED, DialogStatus.CLOSED},
    DialogStatus.WAITING_EMPLOYEE: {DialogStatus.IN_PROGRESS, DialogStatus.CLOSED},
    DialogStatus.RESOLVED: {DialogStatus.CLOSED, DialogStatus.IN_PROGRESS},
    DialogStatus.CLOSED: {DialogStatus.OPEN, DialogStatus.IN_PROGRESS},
}


def create_dialog(client_id: int, employee_id: int | None, subject: str, channel: str) -> Dialog:
    dialog = Dialog(client_id=client_id, responsible_employee_id=employee_id, subject=subject, channel=channel)
    db.session.add(dialog)
    db.session.commit()
    return dialog


def update_dialog(dialog: Dialog, client_id: int, employee_id: int | None, subject: str, channel: str) -> Dialog:
    dialog.client_id, dialog.responsible_employee_id = client_id, employee_id
    dialog.subject, dialog.channel = subject, channel
    db.session.commit()
    return dialog


def delete_dialog(dialog: Dialog) -> None:
    db.session.delete(dialog)
    db.session.commit()


def assign_employee(dialog: Dialog, employee_id: int | None) -> Dialog:
    dialog.responsible_employee_id = employee_id
    db.session.commit()
    return dialog


def change_status(dialog: Dialog, status: DialogStatus) -> Dialog:
    if status != dialog.status and status not in ALLOWED_TRANSITIONS[dialog.status]:
        raise ValueError("Недопустимый переход статуса")
    dialog.status = status
    dialog.closed_at = datetime.now(timezone.utc) if status == DialogStatus.CLOSED else None
    db.session.commit()
    return dialog
