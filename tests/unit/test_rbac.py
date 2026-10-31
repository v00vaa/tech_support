"""Security, delegation and permission tests for RBAC."""

import pytest

from app.extensions import db
from app.models import (
    AuthorType,
    Client,
    Employee,
    Message,
    Permission,
    Role,
)
from app.services.access_control_service import has_permission
from app.services.message_service import create_message
from app.services.rbac_service import ensure_rbac_catalogue
from app.services.role_service import (
    assign_employee_roles,
    save_role,
    update_employee_active_state,
)
from app.services.dialog_service import create_dialog


def _employee(email: str, roles: list[Role], name: str = "Test") -> Employee:
    employee = Employee(
        name=name,
        email=email,
        position="Test",
        password_hash="",
        is_active=True,
    )
    employee.set_password("test-password-long")
    employee.roles = roles
    db.session.add(employee)
    db.session.commit()
    return employee


def _login(client, employee: Employee) -> None:
    with client.session_transaction() as session:
        session["_user_id"] = str(employee.id)
        session["_fresh"] = True


def test_rbac_catalogue_is_idempotent(app) -> None:
    with app.app_context():
        db.create_all()
        first = ensure_rbac_catalogue()
        second = ensure_rbac_catalogue()
        assert first[0].id == second[0].id
        assert db.session.scalar(db.select(db.func.count()).select_from(Role)) == 2
        assert db.session.scalar(db.select(db.func.count()).select_from(Permission)) > 0


def test_employee_can_have_multiple_roles(app) -> None:
    with app.app_context():
        db.create_all()
        administrator, support = ensure_rbac_catalogue()
        employee = _employee("multi@example.com", [support], "Multi")
        assert has_permission(employee, "dialogs.reply")
        assert not has_permission(employee, "employees.create")
        employee.roles.append(administrator)
        db.session.commit()
        assert has_permission(employee, "employees.create")


def test_support_role_cannot_open_employee_management(app, client) -> None:
    with app.app_context():
        db.create_all()
        _, support = ensure_rbac_catalogue()
        employee = _employee("support@example.com", [support], "Support")
        _login(client, employee)
    response = client.get("/employees")
    assert response.status_code == 403


def test_support_role_can_open_dialogs(app, client) -> None:
    with app.app_context():
        db.create_all()
        _, support = ensure_rbac_catalogue()
        employee = _employee("support2@example.com", [support], "Support")
        _login(client, employee)
    response = client.get("/dialogs")
    assert response.status_code == 200


def test_actor_cannot_grant_permissions_they_do_not_have(app) -> None:
    with app.app_context():
        db.create_all()
        _, support = ensure_rbac_catalogue()
        actor = _employee("delegator@example.com", [support])
        with pytest.raises(ValueError, match="права назначать разрешения"):
            save_role(
                actor,
                role=None,
                code="limited_manager",
                name="Ограниченный руководитель",
                description=None,
                permission_codes={"employees.create"},
                is_active=True,
            )


def test_employee_cannot_assign_administrator_role_to_self(app) -> None:
    with app.app_context():
        db.create_all()
        administrator, _ = ensure_rbac_catalogue()
        actor = _employee("admin-self@example.com", [administrator])
        with pytest.raises(ValueError, match="самому себе"):
            assign_employee_roles(actor, actor, [administrator])


def test_last_active_administrator_cannot_be_deactivated(app) -> None:
    with app.app_context():
        db.create_all()
        administrator, _ = ensure_rbac_catalogue()
        employee = _employee("last-admin@example.com", [administrator])
        with pytest.raises(ValueError, match="последнего активного администратора"):
            update_employee_active_state(employee, False)


def test_last_active_administrator_can_be_deactivated_if_another_exists(app) -> None:
    with app.app_context():
        db.create_all()
        administrator, _ = ensure_rbac_catalogue()
        first = _employee("admin-one@example.com", [administrator], "Admin One")
        _employee("admin-two@example.com", [administrator], "Admin Two")
        update_employee_active_state(first, False)
        assert first.is_active is False


def test_internal_messages_are_hidden_from_users_without_note_permission(app, client) -> None:
    with app.app_context():
        db.create_all()
        ensure_rbac_catalogue()
        read_only = Role(
            code="dialog_reader",
            name="Читатель диалогов",
            is_system=False,
            is_active=True,
            permissions=[
                db.session.scalar(
                    db.select(Permission).where(Permission.code == "dialogs.view")
                )
            ],
        )
        db.session.add(read_only)
        employee = _employee("reader@example.com", [read_only], "Reader")
        customer = Client(name="Customer", email="customer@example.com")
        db.session.add(customer)
        db.session.commit()
        dialog = create_dialog(customer.id, None, "Test dialog", "Web")
        create_message(dialog.id, AuthorType.EMPLOYEE, employee.id, "Public")
        create_message(dialog.id, AuthorType.EMPLOYEE, employee.id, "Private", is_internal=True)
        _login(client, employee)
        dialog_id = dialog.id

    response = client.get(f"/api/v1/dialogs/{dialog_id}/messages")
    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload) == 1
    assert payload[0]["text"] == "Public"
