"""CRUD and authorization tests for the JSON API."""

from collections.abc import Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app.extensions import db
from app.models import AuthorType, Client, Dialog, DialogStatus, Employee, Permission, Role
from app.services.dialog_service import create_dialog
from app.services.message_service import create_message
from app.services.rbac_service import ensure_rbac_catalogue


@pytest.fixture
def api_client(app: Flask, client: FlaskClient) -> Iterator[FlaskClient]:
    with app.app_context():
        db.create_all()
        administrator_role, _ = ensure_rbac_catalogue()
        administrator = Employee(
            name="API Administrator",
            email="api-admin@example.com",
            position="Administrator",
            password_hash="",
            is_active=True,
        )
        administrator.set_password("API-password-123!")
        administrator.roles = [administrator_role]
        customer = Client(name="API Customer", email="api-customer@example.com")
        customer.set_password("API-customer-password-123!")
        db.session.add_all([administrator, customer])
        db.session.commit()
        dialog = create_dialog(customer.id, administrator.id, "API dialog", "API")
        create_message(
            dialog.id,
            AuthorType.EMPLOYEE,
            administrator.id,
            "Public API message",
        )
        create_message(
            dialog.id,
            AuthorType.EMPLOYEE,
            administrator.id,
            "Internal API note",
            is_internal=True,
        )
        administrator_id = administrator.id

    with client.session_transaction() as session:
        session["_user_id"] = str(administrator_id)
        session["_fresh"] = True

    yield client

    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_api_requires_authentication(app: Flask) -> None:
    response = app.test_client().get("/api/v1/clients")

    assert response.status_code == 401
    assert response.json is not None
    assert response.json["error"]["code"] == "Unauthorized"


def test_clients_api_lists_and_rejects_manual_creation(
    api_client: FlaskClient,
) -> None:
    listed = api_client.get("/api/v1/clients")
    assert listed.status_code == 200
    assert len(listed.get_json()) == 1

    forbidden = api_client.post(
        "/api/v1/clients",
        json={
            "name": "Manual API customer",
            "email": "manual-api@example.com",
            "phone": "+72222222222",
        },
    )
    assert forbidden.status_code == 403


def test_employees_api_lists_validates_and_creates_records(
    api_client: FlaskClient,
) -> None:
    listed = api_client.get("/api/v1/employees")
    assert listed.status_code == 200
    assert len(listed.get_json()) == 1

    invalid = api_client.post("/api/v1/employees", json={"name": "Incomplete"})
    assert invalid.status_code == 400

    created = api_client.post(
        "/api/v1/employees",
        json={
            "name": "API Agent",
            "email": "api-agent@example.com",
            "password": "Agent-password-123!",
        },
    )
    assert created.status_code == 201
    assert created.json["is_active"] is True
    assert created.json["position"] == "Специалист поддержки"


def test_dialogs_api_is_read_only_for_employee_clients(
    api_client: FlaskClient,
) -> None:
    listed = api_client.get("/api/v1/dialogs")
    assert listed.status_code == 200
    assert len(listed.get_json()) == 1

    forbidden = api_client.post(
        "/api/v1/dialogs",
        json={"client_id": 1, "subject": "Employee-created request"},
    )
    assert forbidden.status_code == 403

    with api_client.application.app_context():
        dialog = db.session.scalar(db.select(Dialog).where(Dialog.subject == "API dialog"))
        assert dialog is not None
        dialog_id = dialog.id

    detail = api_client.get(f"/api/v1/dialogs/{dialog_id}")
    assert detail.status_code == 200
    assert detail.json["subject"] == "API dialog"


def test_messages_api_filters_internal_notes_and_creates_messages(
    api_client: FlaskClient,
) -> None:
    with api_client.application.app_context():
        from app.models import Dialog

        dialog = db.session.scalar(db.select(Dialog).where(Dialog.subject == "API dialog"))
        assert dialog is not None
        dialog_id = dialog.id

    listed = api_client.get(f"/api/v1/dialogs/{dialog_id}/messages")
    assert listed.status_code == 200
    assert len(listed.get_json()) == 2
    assert {item["text"] for item in listed.get_json()} == {
        "Public API message",
        "Internal API note",
    }

    invalid = api_client.post(
        f"/api/v1/dialogs/{dialog_id}/messages",
        json={"is_internal": False},
    )
    assert invalid.status_code == 400

    created = api_client.post(
        f"/api/v1/dialogs/{dialog_id}/messages",
        json={"text": "Created through API"},
    )
    assert created.status_code == 201
    assert created.json["author_type"] == "EMPLOYEE"
    assert created.json["is_internal"] is False

    internal = api_client.post(
        f"/api/v1/dialogs/{dialog_id}/messages",
        json={"text": "Internal through API", "is_internal": True},
    )
    assert internal.status_code == 201
    assert internal.json["is_internal"] is True


def test_employee_api_lists_only_objects_in_active_role_scope(
    api_client: FlaskClient,
) -> None:
    with api_client.application.app_context():
        ensure_rbac_catalogue()
        customer = db.session.scalar(
            db.select(Client).where(Client.email == "api-customer@example.com")
        )
        administrator = db.session.scalar(
            db.select(Employee).where(Employee.email == "api-admin@example.com")
        )
        assert customer is not None
        assert administrator is not None

        role = db.session.scalar(db.select(Role).where(Role.code == "api_limited_role"))
        if role is None:
            role = Role(code="api_limited_role", name="API limited role")
            role.permissions = list(
                db.session.scalars(
                    db.select(Permission).where(
                        Permission.code.in_(["clients.view", "dialogs.view", "dialogs.reply"])
                    )
                )
            )
            db.session.add(role)

        scoped_employee = Employee(
            name="Scoped API Agent",
            email="scoped-api-agent@example.com",
            position="Agent",
            password_hash="",
            is_active=True,
            roles=[role],
        )
        scoped_employee.set_password("Scoped-password-123!")
        hidden_customer = Client(
            name="Hidden API Customer",
            email="hidden-api-customer@example.com",
        )
        db.session.add_all([scoped_employee, hidden_customer])
        db.session.flush()

        visible_dialog = Dialog(
            client_id=customer.id,
            assigned_role_id=role.id,
            subject="Visible to scoped agent",
            channel="API",
        )
        hidden_dialog = Dialog(
            client_id=hidden_customer.id,
            responsible_employee_id=administrator.id,
            subject="Hidden from scoped agent",
            channel="API",
        )
        claimed_dialog = Dialog(
            client_id=hidden_customer.id,
            responsible_employee_id=administrator.id,
            assigned_role_id=role.id,
            subject="Claimed by another employee",
            channel="API",
            status=DialogStatus.IN_PROGRESS,
        )
        closed_queue_dialog = Dialog(
            client_id=hidden_customer.id,
            assigned_role_id=role.id,
            subject="Closed queue dialog",
            channel="API",
            status=DialogStatus.CLOSED,
        )
        special_role = Role(
            code="api_special_role",
            name="API special role",
            role_type="SPECIAL",
        )
        db.session.add(special_role)
        db.session.flush()
        scoped_employee.roles.append(special_role)
        special_role_dialog = Dialog(
            client_id=hidden_customer.id,
            assigned_role_id=special_role.id,
            subject="Special role dialog",
            channel="API",
        )
        owned_closed_dialog = Dialog(
            client_id=customer.id,
            responsible_employee_id=scoped_employee.id,
            subject="Owned closed dialog",
            channel="API",
            status=DialogStatus.CLOSED,
        )
        db.session.add_all(
            [
                visible_dialog,
                hidden_dialog,
                claimed_dialog,
                closed_queue_dialog,
                special_role_dialog,
                owned_closed_dialog,
            ]
        )
        db.session.flush()
        create_message(
            visible_dialog.id,
            AuthorType.EMPLOYEE,
            administrator.id,
            "Public scoped message",
        )
        create_message(
            visible_dialog.id,
            AuthorType.EMPLOYEE,
            administrator.id,
            "Private scoped note",
            is_internal=True,
        )
        scoped_employee_id = scoped_employee.id
        hidden_dialog_ids = [
            hidden_dialog.id,
            claimed_dialog.id,
            closed_queue_dialog.id,
            special_role_dialog.id,
        ]
        visible_dialog_ids = [visible_dialog.id, owned_closed_dialog.id]

    with api_client.session_transaction() as session:
        session["_user_id"] = f"employee:{scoped_employee_id}"
        session["_fresh"] = True

    dialogs_response = api_client.get("/api/v1/dialogs")
    assert dialogs_response.status_code == 200
    assert [item["id"] for item in dialogs_response.get_json()] == visible_dialog_ids

    clients_response = api_client.get("/api/v1/clients")
    assert clients_response.status_code == 200
    assert len(clients_response.get_json()) == 1
    assert clients_response.get_json()[0]["email"] == "api-customer@example.com"

    for hidden_dialog_id in hidden_dialog_ids:
        hidden_detail = api_client.get(f"/api/v1/dialogs/{hidden_dialog_id}")
        assert hidden_detail.status_code == 404
        hidden_messages = api_client.get(f"/api/v1/dialogs/{hidden_dialog_id}/messages")
        assert hidden_messages.status_code == 404

    visible_messages = api_client.get(f"/api/v1/dialogs/{visible_dialog_ids[0]}/messages")
    assert visible_messages.status_code == 200
    assert [item["text"] for item in visible_messages.get_json()] == ["Public scoped message"]


def test_client_account_cannot_use_employee_json_api(
    api_client: FlaskClient,
) -> None:
    with api_client.application.app_context():
        customer = db.session.scalar(
            db.select(Client).where(Client.email == "api-customer@example.com")
        )
        assert customer is not None
        customer_id = customer.id

    with api_client.session_transaction() as session:
        session["_user_id"] = f"client:{customer_id}"
        session["_fresh"] = True

    forbidden = api_client.get("/api/v1/clients")
    assert forbidden.status_code == 403

    health = api_client.get("/api/v1/health/live")
    assert health.status_code == 200


def test_api_rejects_non_object_json_and_non_boolean_flags(
    api_client: FlaskClient,
) -> None:
    dialog_id = api_client.get("/api/v1/dialogs").get_json()[0]["id"]
    non_object = api_client.post(
        f"/api/v1/dialogs/{dialog_id}/messages",
        json=["not", "an", "object"],
    )
    assert non_object.status_code == 400

    invalid_flag = api_client.post(
        "/api/v1/employees",
        json={
            "name": "Invalid Flag Agent",
            "email": "invalid-flag@example.com",
            "password": "Agent-password-123!",
            "is_active": "false",
        },
    )
    assert invalid_flag.status_code == 400
