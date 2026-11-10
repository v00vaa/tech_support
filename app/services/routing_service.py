"""Role routing configuration and dialog queue transfer operations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models.dialog import Dialog, DialogStatus
from app.models.employee import Employee
from app.models.role import Role
from app.models.role_route import RoleRoute
from app.services.access_control_service import has_permission


def _validate_operational_role(role: Role) -> None:
    if (
        role.role_type != "MAIN"
        or role.scope_role_id is not None
        or role.code == "administrator"
        or not role.is_active
    ):
        raise ValueError("Маршрутизация доступна только между активными основными ролями.")


def save_role_route(
    actor: Employee,
    *,
    source_role: Role,
    target_role: Role,
    is_default: bool,
    auto_forward_after_minutes: int | None,
) -> RoleRoute:
    """Create or update one outgoing route; only one default is allowed per source."""
    if not has_permission(actor, "roles.manage_routing"):
        raise ValueError("Недостаточно прав для настройки маршрутизации.")
    _validate_operational_role(source_role)
    _validate_operational_role(target_role)
    if source_role.id == target_role.id:
        raise ValueError("Нельзя направлять роль саму в себя.")
    if auto_forward_after_minutes is not None:
        if not is_default:
            raise ValueError("Время автопередачи можно задать только для маршрута по умолчанию.")
        if not 1 <= auto_forward_after_minutes <= 10080:
            raise ValueError("Время автопередачи должно быть от 1 до 10080 минут.")

    route = db.session.scalar(
        select(RoleRoute).where(
            RoleRoute.source_role_id == source_role.id,
            RoleRoute.target_role_id == target_role.id,
        )
    )
    if route is None:
        route = RoleRoute(source_role=source_role, target_role=target_role)
        db.session.add(route)

    if is_default:
        for other in source_role.outgoing_routes:
            if other is not route:
                other.is_default = False
                other.auto_forward_after_minutes = None
    route.is_default = is_default
    route.auto_forward_after_minutes = auto_forward_after_minutes if is_default else None
    db.session.commit()
    return route


def delete_role_route(actor: Employee, route: RoleRoute) -> None:
    """Delete an outgoing route after checking routing administration permission."""
    if not has_permission(actor, "roles.manage_routing"):
        raise ValueError("Недостаточно прав для настройки маршрутизации.")
    db.session.delete(route)
    db.session.commit()


def route_dialog_to_role(
    actor: Employee,
    dialog: Dialog,
    target_role: Role,
) -> Dialog:
    """Transfer a dialog to a role reachable from its current queue role."""
    if not has_permission(actor, "dialogs.route_to_role"):
        raise ValueError("Недостаточно прав для передачи диалога между ролями.")
    _validate_operational_role(target_role)
    if dialog.status in {DialogStatus.RESOLVED, DialogStatus.CLOSED}:
        raise ValueError("Нельзя передать закрытый или решенный диалог.")
    if dialog.assigned_role_id is not None:
        route = db.session.scalar(
            select(RoleRoute).where(
                RoleRoute.source_role_id == dialog.assigned_role_id,
                RoleRoute.target_role_id == target_role.id,
            )
        )
        if route is None:
            raise ValueError("Для этих ролей не настроено направление передачи.")
    dialog.assigned_role = target_role
    dialog.role_assigned_at = datetime.now(UTC)
    dialog.responsible_employee_id = None
    db.session.commit()
    return dialog


def process_due_auto_forwards(*, now: datetime | None = None, limit: int = 100) -> int:
    """Move queued dialogs through each source role's default route after its timeout."""
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)
    routes = db.session.scalars(
        select(RoleRoute).where(
            RoleRoute.is_default.is_(True),
            RoleRoute.auto_forward_after_minutes.is_not(None),
        )
    ).all()
    transferred = 0
    for route in routes:
        if transferred >= limit:
            break
        if not route.source_role.is_active or not route.target_role.is_active:
            continue
        threshold = current_time - timedelta(minutes=route.auto_forward_after_minutes or 0)
        dialogs = db.session.scalars(
            select(Dialog)
            .where(
                Dialog.assigned_role_id == route.source_role_id,
                Dialog.responsible_employee_id.is_(None),
                Dialog.status.not_in([DialogStatus.RESOLVED, DialogStatus.CLOSED]),
                Dialog.role_assigned_at.is_not(None),
            )
            .order_by(Dialog.role_assigned_at)
            .limit(limit - transferred)
        ).all()
        for dialog in dialogs:
            assigned_at = dialog.role_assigned_at
            if assigned_at is None:
                continue
            if assigned_at.tzinfo is None:
                assigned_at = assigned_at.replace(tzinfo=UTC)
            if assigned_at <= threshold:
                dialog.assigned_role = route.target_role
                dialog.role_assigned_at = current_time
                transferred += 1
    if transferred:
        db.session.commit()
    return transferred
