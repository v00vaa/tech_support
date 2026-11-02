"""Unit tests for CRUD services and permission policies."""

import pytest

from app.extensions import db
from app.models import AuthorType, Client, Dialog, DialogStatus, Employee, Message, Permission, Role
from app.services import client_service, dialog_service, employee_service, message_service
from app.services.access_control_service import (
    can_delegate_permissions,
    ensure_another_active_administrator,
    has_permission,
    permission_codes,
)
from app.services.rbac_service import ensure_rbac_catalogue
from app.services.role_service import save_role


def _employee(email: str, roles: list[Role] | None = None) -> Employee:
    employee = Employee(
        name="Service User",
        email=email,
        position="Support",
        password_hash="",
        is_active=True,
    )
    employee.set_password("Service-password-123!")
    employee.roles = roles or []
    db.session.add(employee)
    db.session.commit()
    return employee


def test_client_service_create_update_and_delete(app) -> None:
    with app.app_context():
        db.create_all()

        customer = client_service.create_client(
            "Initial Client",
            "initial-client@example.com",
            "+70000000000",
        )
        assert customer.id is not None
        assert customer.phone == "+70000000000"

        client_service.update_client(
            customer,
            "Updated Client",
            "updated-client@example.com",
            "",
        )
        assert customer.name == "Updated Client"
        assert customer.email == "updated-client@example.com"
        assert customer.phone is None

        client_service.delete_client(customer)
        assert db.session.get(Client, customer.id) is None


def test_employee_service_create_update_and_delete(app) -> None:
    with app.app_context():
        db.create_all()

        employee = employee_service.create_employee(
            "Initial Employee",
            "initial-employee@example.com",
            "Support",
            "Employee-password-123!",
            True,
        )
        assert employee.check_password("Employee-password-123!")

        employee_service.update_employee(
            employee,
            "Updated Employee",
            "updated-employee@example.com",
            "Senior Support",
            False,
        )
        assert employee.name == "Updated Employee"
        assert employee.email == "updated-employee@example.com"
        assert employee.position == "Senior Support"
        assert employee.is_active is False

        employee_service.delete_employee(employee)
        assert db.session.get(Employee, employee.id) is None


def test_dialog_service_crud_assignment_and_status_transitions(app) -> None:
    with app.app_context():
        db.create_all()
        customer = Client(name="Dialog Client", email="dialog-client@example.com")
        employee = _employee("dialog-agent@example.com")
        db.session.add(customer)
        db.session.commit()

        dialog = dialog_service.create_dialog(customer.id, employee.id, "Initial", "Web")
        assert dialog.status == DialogStatus.OPEN

        dialog_service.update_dialog(dialog, customer.id, None, "Updated", "API")
        assert dialog.subject == "Updated"
        assert dialog.channel == "API"
        assert dialog.responsible_employee_id is None

        dialog_service.assign_employee(dialog, employee.id)
        assert dialog.responsible_employee_id == employee.id

        dialog_service.change_status(dialog, DialogStatus.IN_PROGRESS)
        assert dialog.status == DialogStatus.IN_PROGRESS
        dialog_service.change_status(dialog, DialogStatus.CLOSED)
        assert dialog.status == DialogStatus.CLOSED
        assert dialog.closed_at is not None

        with pytest.raises(ValueError, match="Недопустимый переход"):
            dialog_service.change_status(dialog, DialogStatus.WAITING_CLIENT)

        dialog_service.delete_dialog(dialog)
        assert db.session.get(Dialog, dialog.id) is None


def test_message_service_updates_and_soft_deletes(app) -> None:
    with app.app_context():
        db.create_all()
        customer = Client(name="Message Client", email="message-client@example.com")
        db.session.add(customer)
        db.session.commit()
        dialog = dialog_service.create_dialog(customer.id, None, "Messages", "Web")

        message = message_service.create_message(
            dialog.id,
            AuthorType.CLIENT,
            customer.id,
            "Initial message",
        )
        message_service.update_message(message, "Updated message")
        assert message.text == "Updated message"
        assert message.deleted_at is None

        message_service.delete_message(message)
        assert message.deleted_at is not None
        assert db.session.get(Message, message.id) is message


def test_permission_helpers_respect_employee_and_role_activity(app) -> None:
    with app.app_context():
        db.create_all()
        administrator, support = ensure_rbac_catalogue()
        employee = _employee("permission-user@example.com", [support])

        assert "dialogs.reply" in permission_codes(employee)
        assert has_permission(employee, "dialogs.reply")
        assert not has_permission(employee, "employees.create")
        assert can_delegate_permissions(employee, {"dialogs.reply"})
        assert not can_delegate_permissions(employee, {"employees.create"})

        support.is_active = False
        db.session.commit()
        assert permission_codes(employee) == set()
        assert not has_permission(employee, "dialogs.reply")

        support.is_active = True
        employee.is_active = False
        db.session.commit()
        assert permission_codes(employee) == set()
        assert not has_permission(employee, "dialogs.reply")
        assert administrator.code == "administrator"


def test_last_administrator_guard_allows_safe_cases_and_rejects_last_admin(
    app,
) -> None:
    with app.app_context():
        db.create_all()
        administrator_role, _ = ensure_rbac_catalogue()
        first = _employee("guard-admin-one@example.com", [administrator_role])

        with pytest.raises(ValueError, match="последнего активного администратора"):
            ensure_another_active_administrator(
                first,
                will_remain_administrator=False,
            )

        ensure_another_active_administrator(
            first,
            will_remain_administrator=True,
        )

        _employee("guard-admin-two@example.com", [administrator_role])
        ensure_another_active_administrator(
            first,
            will_remain_administrator=False,
        )


def test_save_role_validates_and_persists_custom_roles(app) -> None:
    with app.app_context():
        db.create_all()
        administrator, _ = ensure_rbac_catalogue()
        actor = _employee("role-service-admin@example.com", [administrator])
        permission = db.session.scalar(
            db.select(Permission).where(Permission.code == "dialogs.view")
        )
        assert permission is not None

        role = save_role(
            actor,
            role=None,
            code="quality_manager",
            name="Quality Manager",
            description="Initial description",
            permission_codes={"dialogs.view"},
            is_active=True,
        )
        assert role.code == "quality_manager"
        assert {item.code for item in role.permissions} == {"dialogs.view"}

        save_role(
            actor,
            role=role,
            code="quality_manager",
            name="Updated Quality Manager",
            description=None,
            permission_codes={"dialogs.view"},
            is_active=False,
        )
        assert role.name == "Updated Quality Manager"
        assert role.description is None
        assert role.is_active is False

        with pytest.raises(ValueError, match="Код роли"):
            save_role(
                actor,
                role=None,
                code="invalid-code",
                name="Invalid",
                description=None,
                permission_codes=set(),
                is_active=True,
            )

        with pytest.raises(ValueError, match="неизвестное разрешение"):
            save_role(
                actor,
                role=None,
                code="unknown_permission_role",
                name="Unknown Permission",
                description=None,
                permission_codes={"missing.permission"},
                is_active=True,
            )

        with pytest.raises(ValueError, match="уже существует"):
            save_role(
                actor,
                role=None,
                code="quality_manager",
                name="Duplicate",
                description=None,
                permission_codes=set(),
                is_active=True,
            )

        with pytest.raises(ValueError, match="Системные роли"):
            save_role(
                actor,
                role=administrator,
                code="administrator",
                name="Administrator",
                description=None,
                permission_codes=set(),
                is_active=True,
            )


def test_scoped_special_roles_are_created_idempotently(app) -> None:
    from app.services.role_service import ensure_special_roles

    with app.app_context():
        db.create_all()
        ensure_rbac_catalogue()
        main_role = Role(code="first_line", name="Первая линия")
        db.session.add(main_role)
        db.session.flush()

        manager, hr = ensure_special_roles(main_role)
        db.session.commit()
        manager_again, hr_again = ensure_special_roles(main_role)

        assert manager.id == manager_again.id
        assert hr.id == hr_again.id
        assert manager.role_type == "MANAGER"
        assert manager.scope_role_id == main_role.id
        assert {permission.code for permission in manager.permissions} == {
            "roles.view_scope_notifications"
        }
        assert hr.role_type == "HR"
        assert hr.scope_role_id == main_role.id
        assert {permission.code for permission in hr.permissions} == {
            "roles.manage_scoped_members"
        }


def test_scoped_hr_can_manage_only_its_main_role(app) -> None:
    from app.services.role_service import ensure_special_roles, manage_role_members

    with app.app_context():
        db.create_all()
        ensure_rbac_catalogue()
        first_line = Role(code="first_line", name="Первая линия")
        second_line = Role(code="second_line", name="Вторая линия")
        db.session.add_all([first_line, second_line])
        db.session.flush()
        _, first_line_hr = ensure_special_roles(first_line)
        _, second_line_hr = ensure_special_roles(second_line)
        actor = _employee("scoped-hr@example.com", [first_line, first_line_hr])
        target = _employee("scoped-target@example.com", [second_line])

        with pytest.raises(ValueError, match="этой роли"):
            manage_role_members(actor, target, second_line, add=True)

        manage_role_members(actor, target, first_line, add=True)
        assert first_line in target.roles
        assert second_line in target.roles

        manage_role_members(actor, target, first_line, add=False)
        assert first_line not in target.roles
        assert second_line in target.roles
        assert first_line_hr not in target.roles
        assert second_line_hr not in target.roles


def test_global_hr_can_manage_any_main_role(app) -> None:
    from app.services.role_service import ensure_global_hr_role, manage_role_members

    with app.app_context():
        db.create_all()
        ensure_rbac_catalogue()
        global_hr = ensure_global_hr_role()
        first_line = Role(code="first_line", name="Первая линия")
        second_line = Role(code="second_line", name="Вторая линия")
        db.session.add_all([first_line, second_line])
        db.session.flush()
        actor = _employee("global-hr@example.com", [global_hr])
        target = _employee("global-target@example.com")

        manage_role_members(actor, target, first_line, add=True)
        manage_role_members(actor, target, second_line, add=True)
        assert first_line in target.roles
        assert second_line in target.roles
