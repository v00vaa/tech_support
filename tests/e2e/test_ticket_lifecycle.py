"""End-to-end customer request lifecycle through role queues."""

from collections.abc import Iterator

import pytest
from flask import Flask

from app.extensions import db
from app.models import (
    AuthorType,
    Client,
    Dialog,
    DialogStatus,
    Employee,
    Message,
    Permission,
    Role,
)
from app.models.role_route import RoleRoute
from app.services.rbac_service import ensure_rbac_catalogue


@pytest.fixture
def ticket_lifecycle(app: Flask) -> Iterator[dict[str, object]]:
    """Prepare two role queues, one employee and one customer account."""
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    with app.app_context():
        db.create_all()
        _, first_line = ensure_rbac_catalogue()
        first_line.is_first_line = True

        route_permission = db.session.scalar(
            db.select(Permission).where(Permission.code == "dialogs.route_to_role")
        )
        assert route_permission is not None
        if route_permission not in first_line.permissions:
            first_line.permissions.append(route_permission)

        second_line = Role(
            code="ticket_lifecycle_second_line",
            name="Вторая линия",
            is_active=True,
        )
        customer = Client(
            name="Lifecycle Customer",
            login="lifecycle-customer",
            email="lifecycle-customer@example.com",
        )
        customer.set_password("customer-password-123")

        employee = Employee(
            name="Lifecycle Agent",
            email="lifecycle-agent@example.com",
            position="Support",
            password_hash="",
            is_active=True,
        )
        employee.set_password("employee-password-123")
        employee.roles = [first_line, second_line]

        db.session.add_all([second_line, customer, employee])
        db.session.flush()
        db.session.add(
            RoleRoute(
                source_role_id=first_line.id,
                target_role_id=second_line.id,
            )
        )
        db.session.commit()

        ids = {
            "customer": customer.id,
            "employee": employee.id,
            "first_line": first_line.id,
            "second_line": second_line.id,
        }

    yield {"app": app, "ids": ids}

    with app.app_context():
        db.session.remove()
        db.drop_all()


def _ids(system: dict[str, object]) -> dict[str, int]:
    return system["ids"]  # type: ignore[return-value]


def test_customer_request_is_queued_claimed_and_transferred(
    ticket_lifecycle: dict[str, object],
) -> None:
    app = ticket_lifecycle["app"]
    assert isinstance(app, Flask)
    ids = _ids(ticket_lifecycle)

    customer_client = app.test_client()
    employee_client = app.test_client()

    # The customer authenticates and creates a request from the customer portal.
    response = customer_client.post(
        "/client/login",
        data={"login": "lifecycle-customer", "password": "customer-password-123"},
    )
    assert response.status_code == 302
    response = customer_client.post(
        "/portal/dialogs/new",
        data={"subject": "Lifecycle request", "message": "Please help with this request."},
    )
    assert response.status_code == 302

    with app.app_context():
        dialog = db.session.scalar(
            db.select(Dialog).where(Dialog.subject == "Lifecycle request")
        )
        assert dialog is not None
        dialog_id = dialog.id
        assert dialog.client_id == ids["customer"]
        assert dialog.assigned_role_id == ids["first_line"]
        assert dialog.responsible_employee_id is None
        assert dialog.status == DialogStatus.OPEN
        assert dialog.role_assigned_at is not None

    # The employee sees the first-line queue and claims the unassigned request.
    response = employee_client.post(
        "/login",
        data={
            "email": "lifecycle-agent@example.com",
            "password": "employee-password-123",
        },
    )
    assert response.status_code == 302

    queue_response = employee_client.get("/dialogs")
    assert queue_response.status_code == 200
    assert b"Lifecycle request" in queue_response.data

    response = employee_client.post(f"/dialogs/{dialog_id}/claim")
    assert response.status_code == 302

    with app.app_context():
        dialog = db.session.get(Dialog, dialog_id)
        assert dialog is not None
        assert dialog.responsible_employee_id == ids["employee"]
        assert dialog.assigned_role_id == ids["first_line"]
        assert dialog.status == DialogStatus.IN_PROGRESS
        claim_event = db.session.scalar(
            db.select(Message).where(
                Message.dialog_id == dialog_id,
                Message.author_type == AuthorType.SYSTEM,
                Message.text == "Обращение взял в работу сотрудник.",
            )
        )
        assert claim_event is not None

    # The employee transfers the request along the configured role route.
    response = employee_client.post(
        f"/dialogs/{dialog_id}/route",
        data={"target_role_id": str(ids["second_line"])},
    )
    assert response.status_code == 302

    with app.app_context():
        dialog = db.session.get(Dialog, dialog_id)
        assert dialog is not None
        assert dialog.assigned_role_id == ids["second_line"]
        assert dialog.responsible_employee_id is None
        assert dialog.status == DialogStatus.OPEN
        assert dialog.role_assigned_at is not None
        transfer_event = db.session.scalar(
            db.select(Message).where(
                Message.dialog_id == dialog_id,
                Message.author_type == AuthorType.SYSTEM,
                Message.text.like("%передано из роли%"),
            )
        )
        assert transfer_event is not None

    # The transferred request appears in the destination role's queue.
    target_queue_response = employee_client.get("/dialogs")
    assert target_queue_response.status_code == 200
    assert b"Lifecycle request" in target_queue_response.data

    # Internal notes remain invisible in the customer-facing conversation.
    with app.app_context():
        db.session.add(
            Message(
                dialog_id=dialog_id,
                author_type=AuthorType.EMPLOYEE,
                author_id=ids["employee"],
                text="Internal-only investigation note.",
                is_internal=True,
            )
        )
        db.session.commit()

    customer_response = customer_client.get(f"/portal/dialogs/{dialog_id}")
    assert customer_response.status_code == 200
    assert b"Please help with this request." in customer_response.data
    assert b"Internal-only investigation note." not in customer_response.data
