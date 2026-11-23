"""Tests for the global workflow routing editor."""

from collections.abc import Iterator

import pytest
from flask import Flask

from app.extensions import db
from app.models import Employee, Role, RoleRoute
from app.services.rbac_service import ensure_rbac_catalogue


@pytest.fixture
def workflow_system(app: Flask, client) -> Iterator[dict[str, int]]:
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.create_all()
        administrator_role, support_role = ensure_rbac_catalogue()
        target_role = Role(
            code="workflow_target",
            name="Workflow target",
            role_type="MAIN",
            is_active=True,
        )
        administrator = Employee(
            name="Workflow Admin",
            email="workflow-admin@example.com",
            position="Administrator",
            password_hash="unused",
            roles=[administrator_role],
        )
        no_permission = Employee(
            name="Workflow Viewer",
            email="workflow-viewer@example.com",
            position="Viewer",
            password_hash="unused",
        )
        db.session.add_all([target_role, administrator, no_permission])
        db.session.commit()
        ids = {
            "admin": administrator.id,
            "viewer": no_permission.id,
            "source": support_role.id,
            "target": target_role.id,
        }

    with client.session_transaction() as session:
        session["_user_id"] = f"employee:{ids['admin']}"
        session["_fresh"] = True

    yield ids

    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_workflow_editor_creates_and_deletes_route(client, workflow_system) -> None:
    page = client.get("/settings/workflow")
    assert page.status_code == 200
    assert "Рабочие процессы".encode() in page.data

    created = client.post(
        "/settings/workflow",
        data={
            "source_role_id": str(workflow_system["source"]),
            "target_role_id": str(workflow_system["target"]),
            "is_default": "y",
            "auto_forward_after_minutes": "30",
        },
    )
    assert created.status_code == 302

    with client.application.app_context():
        route = db.session.scalar(db.select(RoleRoute))
        assert route is not None
        assert route.source_role_id == workflow_system["source"]
        assert route.target_role_id == workflow_system["target"]
        assert route.is_default
        assert route.auto_forward_after_minutes == 30
        route_id = route.id

    deleted = client.post(f"/settings/workflow/routes/{route_id}/delete")
    assert deleted.status_code == 302
    with client.application.app_context():
        assert db.session.get(RoleRoute, route_id) is None


def test_workflow_editor_rejects_self_routing(client, workflow_system) -> None:
    response = client.post(
        "/settings/workflow",
        data={
            "source_role_id": str(workflow_system["source"]),
            "target_role_id": str(workflow_system["source"]),
            "is_default": "y",
            "auto_forward_after_minutes": "",
        },
    )

    assert response.status_code == 200
    assert "Нельзя направлять роль саму в себя.".encode() in response.data
    with client.application.app_context():
        assert db.session.scalar(db.select(RoleRoute)) is None


def test_workflow_editor_requires_routing_permission(client, workflow_system) -> None:
    with client.session_transaction() as session:
        session["_user_id"] = f"employee:{workflow_system['viewer']}"
        session["_fresh"] = True

    assert client.get("/settings/workflow").status_code == 403
    assert (
        client.post(
            f"/settings/workflow/routes/1/delete",
        ).status_code
        == 403
    )
