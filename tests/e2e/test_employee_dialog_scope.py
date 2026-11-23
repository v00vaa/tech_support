"""Employee object-level authorization tests for direct dialog URLs."""

from collections.abc import Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app.extensions import db
from app.models import (
    Attachment,
    AuthorType,
    Client,
    Dialog,
    DialogStatus,
    Employee,
    Message,
    Role,
)
from app.services.rbac_service import ensure_rbac_catalogue


@pytest.fixture
def employee_dialog_scope(
    app: Flask,
    client: FlaskClient,
) -> Iterator[dict[str, int]]:
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    with app.app_context():
        db.create_all()
        administrator_role, support_role = ensure_rbac_catalogue()

        administrator = Employee(
            name="Scope administrator",
            email="scope-admin@example.com",
            position="Administrator",
            password_hash="",
        )
        administrator.set_password("Admin-password-123!")
        administrator.roles = [administrator_role]

        owner = Employee(
            name="Dialog owner",
            email="dialog-owner@example.com",
            position="Support",
            password_hash="",
        )
        owner.set_password("Owner-password-123!")
        owner.roles = [support_role]

        colleague = Employee(
            name="Role colleague",
            email="role-colleague@example.com",
            position="Support",
            password_hash="",
        )
        colleague.set_password("Colleague-password-123!")
        colleague.roles = [support_role]

        observer_role = Role(
            code="all_permissions_observer",
            name="Observer with broad permissions",
            permissions=list(administrator_role.permissions),
        )
        observer = Employee(
            name="Unassigned observer",
            email="observer@example.com",
            position="Observer",
            password_hash="",
            roles=[observer_role],
        )
        observer.set_password("Observer-password-123!")

        customer = Client(
            name="Scope test customer",
            login="scope-customer",
            email="scope-customer@example.com",
        )
        customer.set_password("Customer-password-123!")
        db.session.add_all([administrator, owner, colleague, observer, customer])
        db.session.flush()

        owned_dialog = Dialog(
            client_id=customer.id,
            responsible_employee_id=owner.id,
            assigned_role_id=support_role.id,
            subject="Private assigned dialog",
            status=DialogStatus.IN_PROGRESS,
            channel="Web",
        )
        queue_dialog = Dialog(
            client_id=customer.id,
            responsible_employee_id=None,
            assigned_role_id=support_role.id,
            subject="Available queue dialog",
            status=DialogStatus.OPEN,
            channel="Web",
        )
        db.session.add_all([owned_dialog, queue_dialog])
        db.session.flush()

        public_message = Message(
            dialog_id=owned_dialog.id,
            author_type=AuthorType.CLIENT,
            author_id=customer.id,
            text="Private customer message",
            is_internal=False,
        )
        db.session.add(public_message)
        db.session.flush()
        attachment = Attachment(
            message_id=public_message.id,
            filename="private.txt",
            storage_key="private.txt",
            content_type="text/plain",
            size_bytes=12,
        )
        db.session.add(attachment)
        db.session.commit()

        ids = {
            "administrator": administrator.id,
            "owner": owner.id,
            "colleague": colleague.id,
            "observer": observer.id,
            "owned_dialog": owned_dialog.id,
            "queue_dialog": queue_dialog.id,
            "message": public_message.id,
            "attachment": attachment.id,
        }

    yield ids

    with app.app_context():
        db.session.remove()
        db.drop_all()


def _login_as(client: FlaskClient, employee_id: int) -> None:
    with client.session_transaction() as session:
        session["_user_id"] = f"employee:{employee_id}"
        session["_fresh"] = True


def test_employee_cannot_access_another_employees_dialog_by_direct_url(
    client: FlaskClient,
    employee_dialog_scope: dict[str, int],
) -> None:
    ids = employee_dialog_scope
    _login_as(client, ids["observer"])

    assert client.get(f"/dialogs/{ids['owned_dialog']}").status_code == 403
    assert client.get(f"/dialogs/{ids['owned_dialog']}/edit").status_code == 403
    assert client.post(f"/dialogs/{ids['owned_dialog']}/delete").status_code == 403
    assert (
        client.post(
            f"/dialogs/{ids['owned_dialog']}/status",
            data={"status": "CLOSED", "submit": "Change"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/dialogs/{ids['owned_dialog']}/assign",
            data={"responsible_employee_id": "0", "submit": "Assign"},
        ).status_code
        == 403
    )
    assert client.post(f"/dialogs/{ids['owned_dialog']}/route").status_code == 403
    assert client.post(f"/dialogs/{ids['owned_dialog']}/claim").status_code == 403
    assert (
        client.post(
            f"/dialogs/{ids['owned_dialog']}/messages",
            data={"text": "Unauthorized message", "submit": "Send"},
        ).status_code
        == 403
    )
    assert client.get(f"/messages/attachments/{ids['attachment']}").status_code == 403
    assert client.get(f"/messages/{ids['message']}/edit").status_code == 403
    assert client.post(f"/messages/{ids['message']}/delete").status_code == 403


def test_employee_can_open_only_their_own_dialogs_and_unclaimed_role_queue(
    client: FlaskClient,
    employee_dialog_scope: dict[str, int],
) -> None:
    ids = employee_dialog_scope
    _login_as(client, ids["colleague"])

    assert client.get(f"/dialogs/{ids['owned_dialog']}").status_code == 403
    queue_response = client.get(f"/dialogs/{ids['queue_dialog']}")
    assert queue_response.status_code == 200
    assert "Available queue dialog" in queue_response.get_data(as_text=True)


def test_administrator_can_open_dialog_assigned_to_another_employee(
    client: FlaskClient,
    employee_dialog_scope: dict[str, int],
) -> None:
    ids = employee_dialog_scope
    _login_as(client, ids["administrator"])

    response = client.get(f"/dialogs/{ids['owned_dialog']}")
    assert response.status_code == 200
    assert "Private assigned dialog" in response.get_data(as_text=True)
