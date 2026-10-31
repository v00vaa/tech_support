"""Business rules for role creation, editing and assignment."""

from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy import select

from app.extensions import db
from app.models.employee import Employee
from app.models.role import Permission, Role
from app.services.access_control_service import (
    can_delegate_permissions,
    ensure_another_active_administrator,
    is_active_administrator,
)


def save_role(
    actor: Employee,
    *,
    role: Role | None,
    code: str,
    name: str,
    description: str | None,
    permission_codes: Iterable[str],
    is_active: bool,
) -> Role:
    """Create or update a custom role without allowing permission escalation."""
    if role is not None and role.is_system:
        raise ValueError("Системные роли нельзя изменять.")

    normalized_code = code.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,79}", normalized_code):
        raise ValueError("Код роли должен содержать латинские буквы, цифры и _, начиная с буквы.")

    duplicate = db.session.scalar(
        select(Role).where(Role.code == normalized_code, Role.id != (role.id if role else -1))
    )
    if duplicate is not None:
        raise ValueError("Роль с таким кодом уже существует.")

    requested_codes = set(permission_codes)
    known_permissions = db.session.scalars(
        select(Permission).where(Permission.code.in_(requested_codes))
    ).all() if requested_codes else []
    if {item.code for item in known_permissions} != requested_codes:
        raise ValueError("Выбрано неизвестное разрешение.")

    current_codes = {item.code for item in role.permissions} if role else set()
    if requested_codes != current_codes and not can_delegate_permissions(actor, {"roles.assign_permissions"}):
        raise ValueError("У вас нет права назначать разрешения ролям.")
    if not can_delegate_permissions(actor, requested_codes):
        raise ValueError("Нельзя назначить разрешения, которыми вы сами не обладаете.")

    if role is None:
        role = Role(code=normalized_code, name=name.strip(), description=description, is_active=is_active)
        db.session.add(role)
    else:
        role.code = normalized_code
        role.name = name.strip()
        role.description = description
        role.is_active = is_active
    role.permissions = list(known_permissions)
    db.session.commit()
    return role


def assign_employee_roles(actor: Employee, employee: Employee, roles: Iterable[Role]) -> None:
    """Assign only roles whose permissions the acting employee can delegate."""
    selected_roles = list(roles)
    current_role_permissions = {
        permission.code
        for role in employee.roles
        for permission in role.permissions
    }
    if not can_delegate_permissions(actor, current_role_permissions):
        raise ValueError("Недостаточно прав для изменения текущего набора ролей сотрудника.")
    if employee.id == actor.id and any(role.code == "administrator" for role in selected_roles):
        raise ValueError("Нельзя назначить роль администратора самому себе.")

    for role in selected_roles:
        if not role.is_active:
            raise ValueError(f"Нельзя назначить отключенную роль «{role.name}».")
        role_codes = {permission.code for permission in role.permissions}
        if not can_delegate_permissions(actor, role_codes):
            raise ValueError(f"Недостаточно прав для назначения роли «{role.name}».")

    will_remain_admin = employee.is_active and any(
        role.code == "administrator" and role.is_active for role in selected_roles
    )
    ensure_another_active_administrator(
        employee,
        will_remain_administrator=will_remain_admin,
    )
    employee.roles = selected_roles
    db.session.commit()


def update_employee_active_state(employee: Employee, is_active: bool) -> None:
    """Change employee activity while preserving at least one active administrator."""
    will_remain_admin = is_active and is_active_administrator(employee)
    ensure_another_active_administrator(
        employee,
        will_remain_administrator=will_remain_admin,
    )
    employee.is_active = is_active
    db.session.commit()


def delete_employee_safely(employee: Employee) -> None:
    """Delete an employee unless this would remove the last active administrator."""
    ensure_another_active_administrator(employee, will_remain_administrator=False)
    db.session.delete(employee)
    db.session.commit()
