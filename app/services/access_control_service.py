"""Permission checks and reusable route protection."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from functools import wraps
from typing import Any, TypeVar, cast

from flask import abort
from flask_login import current_user

from app.models.employee import Employee
from app.models.role import Role

F = TypeVar("F", bound=Callable[..., Any])


def permission_codes(employee: Employee) -> set[str]:
    """Return all permission codes granted to an employee by active roles."""
    if not employee.is_active:
        return set()
    return {
        permission.code
        for role in employee.roles
        if role.is_active
        for permission in role.permissions
    }


def has_permission(employee: Employee, permission_code: str) -> bool:
    """Return whether an active employee has the requested permission."""
    return permission_code in permission_codes(employee)


def can_delegate_permissions(employee: Employee, codes: Iterable[str]) -> bool:
    """Prevent a user from granting permissions they do not possess."""
    return set(codes).issubset(permission_codes(employee))


def is_active_administrator(employee: Employee) -> bool:
    """Return whether the employee currently has the built-in administrator role."""
    return employee.is_active and any(
        role.is_active and role.code == "administrator" for role in employee.roles
    )


def ensure_another_active_administrator(
    employee: Employee,
    *,
    will_remain_administrator: bool,
) -> None:
    """Prevent removal or deactivation of the last active administrator."""
    if not is_active_administrator(employee) or will_remain_administrator:
        return

    from app.extensions import db

    other_admins = db.session.query(Employee.id).join(Employee.roles).filter(
        Employee.is_active,
        Role.code == "administrator",
        Role.is_active,
        Employee.id != employee.id,
    )
    if other_admins.first() is None:
        raise ValueError("Нельзя отключить или лишить роли последнего активного администратора.")


def permission_required(permission_code: str) -> Callable[[F], F]:
    """Protect a view with a permission while keeping login handling separate."""

    def decorator(view: F) -> F:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if not current_user.is_authenticated:
                abort(401)
            if not has_permission(cast(Employee, current_user), permission_code):
                abort(403)
            return view(*args, **kwargs)

        return cast(F, wrapped)

    return decorator
