"""Security and delegation tests for RBAC."""

import pytest

from app.extensions import db
from app.models import Employee
from app.services.access_control_service import ensure_another_active_administrator
from app.services.rbac_service import ensure_rbac_catalogue
from app.services.role_service import assign_employee_roles, save_role, update_employee_active_state


def _employee(email: str, roles: list, name: str = "Test") -> Employee:
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
