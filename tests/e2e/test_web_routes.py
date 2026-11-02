"""Browser workflow tests for authenticated support employees."""

from collections.abc import Iterator

import pytest
from flask.testing import FlaskClient

from app.extensions import db
from app.models import AuthorType, Client, Dialog, Employee, Message, Role
from app.services.dialog_service import create_dialog
from app.services.message_service import create_message
from app.services.rbac_service import ensure_rbac_catalogue


@pytest.fixture
def support_system(app, client: FlaskClient) -> Iterator[dict[str, object]]:
    app.config["WTF_CSRF_ENABLED"] = False

    with app.app_context():
        db.create_all()
        administrator_role, support_role = ensure_rbac_catalogue()

        administrator = Employee(
            name="Administrator",
            email="admin-tests@example.com",
            position="Administrator",
            password_hash="",
            is_active=True,
        )
        administrator.set_password("Admin-password-123!")
        administrator.roles = [administrator_role]

        target_employee = Employee(
            name="Support Agent",
            email="agent-tests@example.com",
            position="Support",
            password_hash="",
            is_active=True,
        )
        target_employee.set_password("Agent-password-123!")
        target_employee.roles = [support_role]

        customer = Client(
            name="Test Customer",
            email="customer-tests@example.com",
            phone="+70000000000",
        )
        db.session.add_all([administrator, target_employee, customer])
        db.session.commit()

        dialog = create_dialog(customer.id, target_employee.id, "Initial dialog", "Web")
        message = create_message(
            dialog.id,
            AuthorType.EMPLOYEE,
            target_employee.id,
            "Initial public message",
        )
        custom_role = Role(
            code="test_custom_role",
            name="Test custom role",
            is_system=False,
            is_active=True,
        )
        db.session.add(custom_role)
        db.session.commit()

        ids = {
            "administrator": administrator.id,
            "employee": target_employee.id,
            "client": customer.id,
            "dialog": dialog.id,
            "message": message.id,
            "role": custom_role.id,
            "support_role": support_role.id,
        }

    with client.session_transaction() as session:
        session["_user_id"] = str(ids["administrator"])
        session["_fresh"] = True

    yield {"client": client, "ids": ids}

    with app.app_context():
        db.session.remove()
        db.drop_all()


def _client(system: dict[str, object]) -> FlaskClient:
    return system["client"]  # type: ignore[return-value]


def _ids(system: dict[str, object]) -> dict[str, int]:
    return system["ids"]  # type: ignore[return-value]


def test_authenticated_employee_can_open_browser_pages(
    support_system: dict[str, object],
) -> None:
    client = _client(support_system)
    ids = _ids(support_system)

    paths = [
        "/",
        "/clients",
        "/clients/create",
        f"/clients/{ids['client']}",
        f"/clients/{ids['client']}/edit",
        "/employees",
        "/employees/create",
        f"/employees/{ids['employee']}",
        f"/employees/{ids['employee']}/edit",
        f"/employees/{ids['employee']}/roles",
        "/dialogs",
        "/dialogs/create",
        f"/dialogs/{ids['dialog']}",
        f"/dialogs/{ids['dialog']}/edit",
        f"/messages/{ids['message']}/edit",
        "/settings",
        "/settings/roles",
        "/settings/roles/create",
        f"/settings/roles/{ids['role']}/edit",
        "/settings/workflow",
    ]

    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path


def test_client_create_edit_and_delete_routes(support_system: dict[str, object]) -> None:
    client = _client(support_system)
    client_id = _ids(support_system)["client"]

    created = client.post(
        "/clients/create",
        data={
            "name": "New Customer",
            "email": "new-customer@example.com",
            "phone": "+71111111111",
            "submit": "Save",
        },
    )
    assert created.status_code == 302

    edited = client.post(
        f"/clients/{client_id}/edit",
        data={
            "name": "Updated Customer",
            "email": "updated-customer@example.com",
            "phone": "",
            "submit": "Save",
        },
    )
    assert edited.status_code == 302

    deleted = client.post(f"/clients/{client_id}/delete")
    assert deleted.status_code == 302

    with client.application.app_context():
        assert db.session.get(Client, client_id) is None
        assert (
            db.session.scalar(
                db.select(Client).where(Client.email == "new-customer@example.com")
            )
            is not None
        )


def test_employee_create_edit_and_deactivate_routes(
    support_system: dict[str, object],
) -> None:
    client = _client(support_system)
    employee_id = _ids(support_system)["employee"]

    created = client.post(
        "/employees/create",
        data={
            "name": "New Agent",
            "email": "new-agent@example.com",
            "position": "Support",
            "password": "New-agent-password-123!",
            "is_active": "y",
            "submit": "Save",
        },
    )
    assert created.status_code == 302

    edited = client.post(
        f"/employees/{employee_id}/edit",
        data={
            "name": "Updated Agent",
            "email": "updated-agent@example.com",
            "position": "Senior Support",
            "is_active": "y",
            "submit": "Save",
        },
    )
    assert edited.status_code == 302

    deactivated = client.post(f"/employees/{employee_id}/delete")
    assert deactivated.status_code == 302

    with client.application.app_context():
        employee = db.session.get(Employee, employee_id)
        assert employee is not None
        assert employee.is_active is False


def test_employee_cannot_deactivate_the_current_account(
    support_system: dict[str, object],
) -> None:
    client = _client(support_system)
    administrator_id = _ids(support_system)["administrator"]

    response = client.post(f"/employees/{administrator_id}/delete")

    assert response.status_code == 302
    with client.application.app_context():
        administrator = db.session.get(Employee, administrator_id)
        assert administrator is not None
        assert administrator.is_active is True


def test_dialog_create_edit_status_assignment_and_delete_routes(
    support_system: dict[str, object],
) -> None:
    client = _client(support_system)
    ids = _ids(support_system)

    created = client.post(
        "/dialogs/create",
        data={
            "client_id": str(ids["client"]),
            "responsible_employee_id": str(ids["employee"]),
            "subject": "New dialog",
            "channel": "Web",
            "submit": "Save",
        },
    )
    assert created.status_code == 302

    dialog_id = ids["dialog"]
    edited = client.post(
        f"/dialogs/{dialog_id}/edit",
        data={
            "client_id": str(ids["client"]),
            "responsible_employee_id": "0",
            "subject": "Updated dialog",
            "channel": "API",
            "submit": "Save",
        },
    )
    assert edited.status_code == 302

    status_changed = client.post(
        f"/dialogs/{dialog_id}/status",
        data={"status": "IN_PROGRESS", "submit": "Change"},
    )
    assert status_changed.status_code == 302

    assigned = client.post(
        f"/dialogs/{dialog_id}/assign",
        data={"responsible_employee_id": str(ids["employee"]), "submit": "Assign"},
    )
    assert assigned.status_code == 302

    with client.application.app_context():
        dialog = db.session.get(Dialog, dialog_id)
        assert dialog is not None
        assert dialog.subject == "Updated dialog"
        assert dialog.status.value == "IN_PROGRESS"
        assert dialog.responsible_employee_id == ids["employee"]

    deleted = client.post(f"/dialogs/{dialog_id}/delete")
    assert deleted.status_code == 302


def test_message_create_edit_and_soft_delete_routes(
    support_system: dict[str, object],
) -> None:
    client = _client(support_system)
    ids = _ids(support_system)
    dialog_id = ids["dialog"]
    message_id = ids["message"]

    created = client.post(
        f"/dialogs/{dialog_id}/messages",
        data={"text": "A public response", "submit": "Send"},
    )
    assert created.status_code == 302

    internal = client.post(
        f"/dialogs/{dialog_id}/messages",
        data={"text": "An internal note", "is_internal": "y", "submit": "Send"},
    )
    assert internal.status_code == 302

    edited = client.post(
        f"/messages/{message_id}/edit",
        data={"text": "Edited public response", "submit": "Save"},
    )
    assert edited.status_code == 302

    deleted = client.post(f"/messages/{message_id}/delete")
    assert deleted.status_code == 302

    with client.application.app_context():
        message = db.session.get(Message, message_id)
        assert message is not None
        assert message.text == "Edited public response"
        assert message.deleted_at is not None
        assert db.session.scalar(
            db.select(Message).where(Message.text == "An internal note")
        ) is not None


def test_employee_roles_and_custom_role_routes(support_system: dict[str, object]) -> None:
    client = _client(support_system)
    ids = _ids(support_system)

    assigned = client.post(
        f"/employees/{ids['employee']}/roles",
        data={"roles": [str(ids["support_role"])], "submit": "Save"},
    )
    assert assigned.status_code == 302

    created = client.post(
        "/settings/roles/create",
        data={
            "code": "qa_manager",
            "name": "QA Manager",
            "description": "Role used in route tests",
            "permissions": ["dialogs.view"],
            "is_active": "y",
            "submit": "Save",
        },
    )
    assert created.status_code == 302

    with client.application.app_context():
        role = db.session.scalar(db.select(Role).where(Role.code == "qa_manager"))
        assert role is not None
        role_id = role.id

    edited = client.post(
        f"/settings/roles/{role_id}/edit",
        data={
            "code": "qa_manager_updated",
            "name": "Updated QA Manager",
            "description": "Updated role description",
            "permissions": ["dialogs.view", "dialogs.reply"],
            "is_active": "y",
            "submit": "Save",
        },
    )
    assert edited.status_code == 302

    with client.application.app_context():
        role = db.session.get(Role, role_id)
        assert role is not None
        assert role.code == "qa_manager_updated"
        assert {permission.code for permission in role.permissions} == {
            "dialogs.view",
            "dialogs.reply",
        }


def test_login_logout_and_password_change_routes(
    app,
    client: FlaskClient,
) -> None:
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        db.create_all()
        administrator_role, _ = ensure_rbac_catalogue()
        employee = Employee(
            name="Login User",
            email="login-user@example.com",
            position="Support",
            password_hash="",
            is_active=True,
            must_change_password=True,
        )
        employee.set_password("Temporary-password-123!")
        employee.roles = [administrator_role]
        db.session.add(employee)
        db.session.commit()
        employee_id = employee.id

    assert client.get("/login").status_code == 200
    invalid_login = client.post(
        "/login",
        data={"email": "login-user@example.com", "password": "wrong-password"},
    )
    assert invalid_login.status_code == 200

    valid_login = client.post(
        "/login",
        data={
            "email": "login-user@example.com",
            "password": "Temporary-password-123!",
        },
    )
    assert valid_login.status_code == 302
    assert valid_login.headers["Location"].endswith("/change-password")

    wrong_current_password = client.post(
        "/change-password",
        data={
            "current_password": "incorrect",
            "new_password": "New-password-123!",
            "confirm_password": "New-password-123!",
        },
    )
    assert wrong_current_password.status_code == 200

    changed = client.post(
        "/change-password",
        data={
            "current_password": "Temporary-password-123!",
            "new_password": "New-password-456!",
            "confirm_password": "New-password-456!",
        },
    )
    assert changed.status_code == 302

    with app.app_context():
        employee = db.session.get(Employee, employee_id)
        assert employee is not None
        assert employee.check_password("New-password-456!")
        assert employee.must_change_password is False

    logged_out = client.post("/logout")
    assert logged_out.status_code == 302
