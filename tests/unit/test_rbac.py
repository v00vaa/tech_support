"""Tests for the initial role and permission foundation."""

import pytest

from app.extensions import db
from app.models import Employee, Permission, Role
from app.services.access_control_service import has_permission
from app.services.rbac_service import ensure_rbac_catalogue


def test_rbac_catalogue_is_idempotent(app) -> None:  # type: ignore[no-untyped-def]
    with app.app_context():
        db.create_all()
        first = ensure_rbac_catalogue()
        second = ensure_rbac_catalogue()
        assert first[0].id == second[0].id
        assert db.session.scalar(db.select(db.func.count()).select_from(Role)) == 2
        assert db.session.scalar(db.select(db.func.count()).select_from(Permission)) > 0


def test_employee_can_have_multiple_roles_and_permissions(app) -> None:  # type: ignore[no-untyped-def]
    with app.app_context():
        db.create_all()
        administrator, support = ensure_rbac_catalogue()
        employee = Employee(name="Test", email="test@example.com", position="Тест", password_hash="")
        employee.set_password("long-test-password")
        employee.roles = [support]
        db.session.add(employee)
        db.session.commit()

        assert has_permission(employee, "dialogs.reply")
        assert not has_permission(employee, "employees.create")
        employee.roles.append(administrator)
        db.session.commit()
        assert has_permission(employee, "employees.create")
