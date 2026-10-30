"""Permission checks and reusable route protection."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from flask import abort
from flask_login import current_user

from app.models.employee import Employee

F = TypeVar("F", bound=Callable[..., Any])


def has_permission(employee: Employee, permission_code: str) -> bool:
    """Return whether an active employee has the requested permission."""
    if not employee.is_active:
        return False
    return any(
        role.is_active and any(permission.code == permission_code for permission in role.permissions)
        for role in employee.roles
    )


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
