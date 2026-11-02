"""CRUD and authorization tests for the JSON API."""

from collections.abc import Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from app.extensions import db
from app.models import AuthorType, Client, Employee
from app.services.dialog_service import create_dialog
from app.services.message_service import create_message
from app.services.rbac_service import ensure_rbac_catalogue


@pytest.fixture
def api_client(app: Flask, client: FlaskClient) -> Iterator[FlaskClient]:
    with app.app_context():
        db.create_all()
        administrator_role, _ = ensure_rbac_catalogue()
        administrator = Employee(
            name="API Administrator",
            email="api-admin@example.com",
            position="Administrator",
            password_hash="",
            is_active=True,
        )
        administrator.set_password("API-password-123!")
        administrator.roles = [administrator_role]
        customer = Client(name="API Customer", email="api-customer@example.com")
        db.session.add_all([administrator, customer])
        db.session.commit()
        dialog = create_dialog(customer.id, administrator.id, "API dialog", "API")
        create_message(
            dialog.id,
            AuthorType.EMPLOYEE,
            administrator.id,
            "Public API message",
        )
        create_message(
            dialog.id,
            AuthorType.EMPLOYEE,
            administrator.id,
            "Internal API note",
            is_internal=True,
        )
        administrator_id = administrator.id

    with client.session_transaction() as session:
        session["_user_id"] = str(administrator_id)
        session["_fresh"] = True

    yield client

    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_api_requires_authentication(app: Flask) -> None:
    response = app.test_client().get("/api/v1/clients")

    assert response.status_code == 401
    assert response.json is not None
    assert response.json["error"]["code"] == "Unauthorized"


def test_clients_api_lists_validates_creates_and_returns_records(
    api_client: FlaskClient,
) -> None:
    empty_list = api_client.get("/api/v1/clients")
    assert empty_list.status_code == 200
    assert len(empty_list.get_json()) == 1

    invalid = api_client.post("/api/v1/clients", json={"name": "Missing email"})
    assert invalid.status_code == 400

    created = api_client.post(
        "/api/v1/clients",
        json={
            "name": "Created through API",
            "email": "created-api@example.com",
            "phone": "+72222222222",
        },
    )
    assert created.status_code == 201
    assert created.json["name"] == "Created through API"
    assert created.json["phone"] == "+72222222222"


def test_employees_api_lists_validates_and_creates_records(
    api_client: FlaskClient,
) -> None:
    listed = api_client.get("/api/v1/employees")
    assert listed.status_code == 200
    assert len(listed.get_json()) == 1

    invalid = api_client.post("/api/v1/employees", json={"name": "Incomplete"})
    assert invalid.status_code == 400

    created = api_client.post(
        "/api/v1/employees",
        json={
            "name": "API Agent",
            "email": "api-agent@example.com",
            "password": "Agent-password-123!",
        },
    )
    assert created.status_code == 201
    assert created.json["is_active"] is True
    assert created.json["position"] == "Специалист поддержки"


def test_dialogs_api_lists_validates_creates_and_returns_details(
    api_client: FlaskClient,
) -> None:
    listed = api_client.get("/api/v1/dialogs")
    assert listed.status_code == 200
    assert len(listed.get_json()) == 1

    invalid = api_client.post("/api/v1/dialogs", json={"subject": "Missing client"})
    assert invalid.status_code == 400

    with api_client.application.app_context():
        customer = db.session.scalar(
            db.select(Client).where(Client.email == "api-customer@example.com")
        )
        assert customer is not None
        customer_id = customer.id

    created = api_client.post(
        "/api/v1/dialogs",
        json={"client_id": customer_id, "subject": "Created through API"},
    )
    assert created.status_code == 201
    assert created.json["channel"] == "API"
    detail = api_client.get(f"/api/v1/dialogs/{created.json['id']}")
    assert detail.status_code == 200
    assert detail.json["subject"] == "Created through API"


def test_messages_api_filters_internal_notes_and_creates_messages(
    api_client: FlaskClient,
) -> None:
    with api_client.application.app_context():
        from app.models import Dialog

        dialog = db.session.scalar(db.select(Dialog).where(Dialog.subject == "API dialog"))
        assert dialog is not None
        dialog_id = dialog.id

    listed = api_client.get(f"/api/v1/dialogs/{dialog_id}/messages")
    assert listed.status_code == 200
    assert len(listed.get_json()) == 2
    assert {item["text"] for item in listed.get_json()} == {
        "Public API message",
        "Internal API note",
    }

    invalid = api_client.post(
        f"/api/v1/dialogs/{dialog_id}/messages",
        json={"is_internal": False},
    )
    assert invalid.status_code == 400

    created = api_client.post(
        f"/api/v1/dialogs/{dialog_id}/messages",
        json={"text": "Created through API"},
    )
    assert created.status_code == 201
    assert created.json["author_type"] == "EMPLOYEE"
    assert created.json["is_internal"] is False

    internal = api_client.post(
        f"/api/v1/dialogs/{dialog_id}/messages",
        json={"text": "Internal through API", "is_internal": True},
    )
    assert internal.status_code == 201
    assert internal.json["is_internal"] is True
