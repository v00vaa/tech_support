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
    if role is not None and role.role_type != "MAIN":
        raise ValueError("Специальные роли нельзя изменять как обычные роли.")

    normalized_code = code.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,79}", normalized_code):
        raise ValueError("Код роли должен содержать латинские буквы, цифры и _, начиная с буквы.")

    duplicate = db.session.scalar(
        select(Role).where(Role.code == normalized_code, Role.id != (role.id if role else -1))
    )
    if duplicate is not None:
        raise ValueError("Роль с таким кодом уже существует.")

    requested_codes = set(permission_codes)
    known_permissions = (
        db.session.scalars(select(Permission).where(Permission.code.in_(requested_codes))).all()
        if requested_codes
        else []
    )
    if {item.code for item in known_permissions} != requested_codes:
        raise ValueError("Выбрано неизвестное разрешение.")

    current_codes = {item.code for item in role.permissions} if role else set()
    if requested_codes != current_codes and not can_delegate_permissions(
        actor, {"roles.assign_permissions"}
    ):
        raise ValueError("У вас нет права назначать разрешения ролям.")
    if not can_delegate_permissions(actor, requested_codes):
        raise ValueError("Нельзя назначить разрешения, которыми вы сами не обладаете.")

    if role is None:
        role = Role(
            code=normalized_code, name=name.strip(), description=description, is_active=is_active
        )
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
        permission.code for role in employee.roles for permission in role.permissions
    }
    if not can_delegate_permissions(actor, current_role_permissions):
        raise ValueError("Недостаточно прав для изменения текущего набора ролей сотрудника.")
    already_administrator = any(
        role.code == "administrator" and role.is_active for role in employee.roles
    )
    adding_administrator = any(
        role.code == "administrator" and role.is_active for role in selected_roles
    )
    if employee.id == actor.id and adding_administrator and not already_administrator:
        raise ValueError("Нельзя назначить роль администратора самому себе.")

    selected_role_ids = {role.id for role in selected_roles}
    for role in selected_roles:
        if not role.is_active:
            raise ValueError(f"Нельзя назначить отключенную роль «{role.name}».")
        if role.role_type in {"MANAGER", "HR"} and role.scope_role_id not in selected_role_ids:
            raise ValueError(
                f"Для назначения роли «{role.name}» сотрудник должен состоять "
                "в соответствующей основной роли."
            )
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


def ensure_special_roles(main_role: Role) -> tuple[Role, Role]:
    """Create the manager and HR roles scoped to one main role, idempotently."""
    if main_role.role_type != "MAIN" or main_role.scope_role_id is not None:
        raise ValueError("Специальные роли можно создавать только для основной роли.")

    manager_permission = db.session.scalar(
        select(Permission).where(Permission.code == "roles.view_scope_notifications")
    )
    hr_permission = db.session.scalar(
        select(Permission).where(Permission.code == "roles.manage_scoped_members")
    )
    if manager_permission is None or hr_permission is None:
        raise ValueError("Сначала необходимо выполнить инициализацию каталога RBAC.")

    manager = db.session.scalar(
        select(Role).where(Role.scope_role_id == main_role.id, Role.role_type == "MANAGER")
    )
    if manager is None:
        manager = Role(
            code=f"manager_{main_role.id}",
            name=f"Начальник — {main_role.name}",
            description=f"Информация и уведомления по роли «{main_role.name}».",
            is_system=True,
            role_type="MANAGER",
            scope_role=main_role,
        )
        db.session.add(manager)
    manager.name = f"Начальник — {main_role.name}"
    manager.description = f"Информация и уведомления по роли «{main_role.name}»."
    manager.permissions = [manager_permission]

    hr = db.session.scalar(
        select(Role).where(Role.scope_role_id == main_role.id, Role.role_type == "HR")
    )
    if hr is None:
        hr = Role(
            code=f"hr_{main_role.id}",
            name=f"HR — {main_role.name}",
            description=f"Управление составом только роли «{main_role.name}».",
            is_system=True,
            role_type="HR",
            scope_role=main_role,
        )
        db.session.add(hr)
    hr.name = f"HR — {main_role.name}"
    hr.description = f"Управление составом только роли «{main_role.name}»."
    hr.permissions = [hr_permission]
    db.session.flush()
    return manager, hr


def ensure_global_hr_role() -> Role:
    """Create the global HR role, which is not scoped to a particular main role."""
    permission = db.session.scalar(
        select(Permission).where(Permission.code == "roles.manage_all_members")
    )
    if permission is None:
        raise ValueError("Сначала необходимо выполнить инициализацию каталога RBAC.")
    role = db.session.scalar(select(Role).where(Role.code == "global_hr"))
    if role is None:
        role = Role(
            code="global_hr",
            name="Глобальный HR",
            description="Управление составом всех основных ролей.",
            is_system=True,
            role_type="GLOBAL_HR",
        )
        db.session.add(role)
    role.permissions = [permission]
    db.session.flush()
    return role


def manage_role_members(
    actor: Employee,
    employee: Employee,
    main_role: Role,
    *,
    add: bool,
) -> None:
    """Add/remove one employee from a main role with strict server-side scope checks."""
    if not actor.is_active or not employee.is_active:
        raise ValueError("Управлять составом можно только для активных сотрудников.")
    if main_role.role_type != "MAIN" or main_role.scope_role_id is not None:
        raise ValueError("Указана некорректная основная роль.")
    if not main_role.is_active:
        raise ValueError("Нельзя изменять состав отключенной роли.")

    is_global_hr = any(
        role.is_active and role.code == "global_hr" and role.role_type == "GLOBAL_HR"
        for role in actor.roles
    )
    is_administrator = is_active_administrator(actor)
    has_scoped_hr = any(
        role.is_active
        and role.role_type == "HR"
        and role.scope_role_id == main_role.id
        and "roles.manage_scoped_members" in {permission.code for permission in role.permissions}
        for role in actor.roles
    )
    if not (is_global_hr or is_administrator or has_scoped_hr):
        raise ValueError("Недостаточно прав для управления сотрудниками этой роли.")

    if add:
        if main_role not in employee.roles:
            employee.roles.append(main_role)
    else:
        if main_role in employee.roles:
            ensure_another_active_administrator(
                employee,
                will_remain_administrator=any(
                    role.code == "administrator" and role.is_active
                    for role in employee.roles
                    if role.id != main_role.id
                ),
            )
            employee.roles.remove(main_role)
        # A scoped manager/HR assignment must not outlive membership in its main role.
        employee.roles = [
            role
            for role in employee.roles
            if role.scope_role_id != main_role.id
        ]
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
