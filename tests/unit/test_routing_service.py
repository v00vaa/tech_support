"""Tests for role-based dialog routing and automatic forwarding."""

from datetime import UTC, datetime, timedelta

import pytest

from app.extensions import db
from app.models import AuthorType, Client, Dialog, DialogStatus, Employee, Message, Role
from app.models.role_route import RoleRoute
from app.services.rbac_service import ensure_rbac_catalogue
from app.services.routing_service import (
    delete_role_route,
    process_due_auto_forwards,
    route_dialog_to_role,
    save_role_route,
)


def _employee(email: str, roles: list[Role]) -> Employee:
    employee = Employee(
        name="Routing Administrator",
        email=email,
        position="Support",
        password_hash="",
        is_active=True,
        roles=roles,
    )
    employee.set_password("routing-test-password")
    db.session.add(employee)
    db.session.flush()
    return employee


def _setup():
    administrator, _ = ensure_rbac_catalogue()
    actor = _employee("routing-admin@example.com", [administrator])
    source = Role(code="routing_source", name="Source")
    target = Role(code="routing_target", name="Target")
    other = Role(code="routing_other", name="Other")
    db.session.add_all([source, target, other])
    actor.roles.append(source)
    customer = Client(name="Routing Customer", email="routing-customer@example.com")
    db.session.add(customer)
    db.session.commit()
    return actor, source, target, other, customer


def test_save_role_route_creates_updates_default_and_rejects_invalid_values(app):
    with app.app_context():
        db.create_all()
        actor, source, target, other, _ = _setup()

        route = save_role_route(
            actor,
            source_role=source,
            target_role=target,
            is_default=True,
            auto_forward_after_minutes=15,
        )
        assert route.id is not None
        assert route.is_default is True
        assert route.auto_forward_after_minutes == 15

        second = save_role_route(
            actor,
            source_role=source,
            target_role=other,
            is_default=True,
            auto_forward_after_minutes=None,
        )
        assert second.is_default is True
        assert route.is_default is False
        assert second.auto_forward_after_minutes is None

        with pytest.raises(ValueError, match="саму в себя"):
            save_role_route(
                actor,
                source_role=source,
                target_role=source,
                is_default=False,
                auto_forward_after_minutes=None,
            )

        with pytest.raises(ValueError, match="только для маршрута"):
            save_role_route(
                actor,
                source_role=source,
                target_role=target,
                is_default=False,
                auto_forward_after_minutes=10,
            )

        with pytest.raises(ValueError, match="от 1 до 10080"):
            save_role_route(
                actor,
                source_role=source,
                target_role=target,
                is_default=True,
                auto_forward_after_minutes=0,
            )

        special = Role(code="routing_special", name="Special", role_type="HR")
        db.session.add(special)
        db.session.commit()
        with pytest.raises(ValueError, match="активными основными ролями"):
            save_role_route(
                actor,
                source_role=special,
                target_role=target,
                is_default=False,
                auto_forward_after_minutes=None,
            )


def test_routing_requires_permission_and_delete_removes_route(app):
    with app.app_context():
        db.create_all()
        actor, source, target, _, _ = _setup()
        route = RoleRoute(source_role=source, target_role=target)
        db.session.add(route)
        db.session.commit()

        unprivileged = _employee("routing-no-permission@example.com", [])
        with pytest.raises(ValueError, match="Недостаточно прав"):
            save_role_route(
                unprivileged,
                source_role=source,
                target_role=target,
                is_default=False,
                auto_forward_after_minutes=None,
            )
        with pytest.raises(ValueError, match="Недостаточно прав"):
            delete_role_route(unprivileged, route)

        delete_role_route(actor, route)
        assert db.session.get(RoleRoute, route.id) is None


def test_route_dialog_requires_allowed_route_and_open_status(app):
    with app.app_context():
        db.create_all()
        actor, source, target, other, customer = _setup()
        dialog = Dialog(
            client_id=customer.id,
            assigned_role=source,
            subject="Route me",
            status=DialogStatus.OPEN,
        )
        db.session.add(dialog)
        db.session.commit()

        with pytest.raises(ValueError, match="не настроено направление"):
            route_dialog_to_role(actor, dialog, other)

        save_role_route(
            actor,
            source_role=source,
            target_role=target,
            is_default=False,
            auto_forward_after_minutes=None,
        )
        route_dialog_to_role(actor, dialog, target)
        assert dialog.assigned_role_id == target.id
        assert dialog.responsible_employee_id is None
        assert dialog.role_assigned_at is not None
        assert dialog.status == DialogStatus.OPEN
        transfer_event = db.session.scalar(
            db.select(Message).where(
                Message.dialog_id == dialog.id,
                Message.author_type == AuthorType.SYSTEM,
                Message.text.like("%передано из роли%"),
            )
        )
        assert transfer_event is not None

        dialog.status = DialogStatus.CLOSED
        db.session.commit()
        with pytest.raises(ValueError, match="закрытый или решенный"):
            route_dialog_to_role(actor, dialog, source)


def test_route_dialog_rejects_actor_outside_source_role(app):
    with app.app_context():
        db.create_all()
        administrator, source, target, _, customer = _setup()
        save_role_route(
            administrator,
            source_role=source,
            target_role=target,
            is_default=False,
            auto_forward_after_minutes=None,
        )
        actor = _employee("routing-outsider@example.com", [administrator.roles[0]])
        dialog = Dialog(
            client_id=customer.id,
            assigned_role=source,
            subject="Wrong source role",
        )
        db.session.add(dialog)
        db.session.commit()

        with pytest.raises(ValueError, match="только сотрудник текущей роли"):
            route_dialog_to_role(actor, dialog, target)


def test_route_dialog_rejects_dialog_without_source_role(app):
    with app.app_context():
        db.create_all()
        administrator, _, target, _, customer = _setup()
        dialog = Dialog(
            client_id=customer.id,
            subject="No source role",
        )
        db.session.add(dialog)
        db.session.commit()

        with pytest.raises(ValueError, match="исходная очередь"):
            route_dialog_to_role(administrator, dialog, target)


def test_route_dialog_rejects_actor_without_permission(app):
    with app.app_context():
        db.create_all()
        actor, source, target, _, customer = _setup()
        save_role_route(
            actor,
            source_role=source,
            target_role=target,
            is_default=False,
            auto_forward_after_minutes=None,
        )
        unprivileged = _employee("routing-no-route-permission@example.com", [])
        dialog = Dialog(
            client_id=customer.id,
            assigned_role=source,
            subject="Forbidden transfer",
        )
        db.session.add(dialog)
        db.session.commit()

        with pytest.raises(ValueError, match="Недостаточно прав"):
            route_dialog_to_role(unprivileged, dialog, target)


def test_process_due_auto_forwards_respects_timeout_status_activity_and_limit(app):
    with app.app_context():
        db.create_all()
        actor, source, target, other, customer = _setup()
        save_role_route(
            actor,
            source_role=source,
            target_role=target,
            is_default=True,
            auto_forward_after_minutes=10,
        )
        now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
        due = Dialog(
            client_id=customer.id,
            assigned_role=source,
            subject="Due",
            status=DialogStatus.OPEN,
            role_assigned_at=now - timedelta(minutes=11),
        )
        recent = Dialog(
            client_id=customer.id,
            assigned_role=source,
            subject="Recent",
            status=DialogStatus.OPEN,
            role_assigned_at=now - timedelta(minutes=5),
        )
        waiting = Dialog(
            client_id=customer.id,
            assigned_role=source,
            subject="Waiting client",
            status=DialogStatus.WAITING_CLIENT,
            role_assigned_at=now - timedelta(minutes=30),
        )
        assigned = Dialog(
            client_id=customer.id,
            assigned_role=source,
            subject="Assigned",
            status=DialogStatus.OPEN,
            responsible_employee=actor,
            role_assigned_at=now - timedelta(minutes=30),
        )
        db.session.add_all([due, recent, waiting, assigned])
        db.session.commit()

        assert process_due_auto_forwards(now=now, limit=1) == 1
        assert due.assigned_role_id == target.id
        assert due.status == DialogStatus.OPEN
        auto_event = db.session.scalar(
            db.select(Message).where(
                Message.dialog_id == due.id,
                Message.author_type == AuthorType.SYSTEM,
                Message.text.like("%автоматически передано%"),
            )
        )
        assert auto_event is not None
        assert recent.assigned_role_id == source.id
        assert waiting.assigned_role_id == source.id
        assert assigned.assigned_role_id == source.id
        assert process_due_auto_forwards(now=now) == 0

        source.is_active = False
        db.session.commit()
        assert process_due_auto_forwards(now=now) == 0


def test_process_due_auto_forwards_normalizes_naive_time_and_ignores_missing_assignment_time(app):
    with app.app_context():
        db.create_all()
        actor, source, target, _, customer = _setup()
        save_role_route(
            actor,
            source_role=source,
            target_role=target,
            is_default=True,
            auto_forward_after_minutes=1,
        )
        dialog = Dialog(
            client_id=customer.id,
            assigned_role=source,
            subject="No assignment timestamp",
            status=DialogStatus.OPEN,
            role_assigned_at=None,
        )
        db.session.add(dialog)
        db.session.commit()

        assert process_due_auto_forwards(now=datetime(2026, 11, 15, 12, 0), limit=10) == 0
        assert dialog.assigned_role_id == source.id
