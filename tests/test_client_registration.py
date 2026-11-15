"""Tests for manual and primary-system customer registration."""

import pytest

from app.extensions import db
from app.models import Client


@pytest.fixture(autouse=True)
def registration_database(app):
    """Create all model tables required by registration routes."""
    with app.app_context():
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()


def test_manual_registration_creates_customer_account(app, client):
    app.config["WTF_CSRF_ENABLED"] = False

    page = client.get("/register")
    assert page.status_code == 200

    response = client.post(
        "/register",
        data={
            "login": "manual-customer",
            "name": "Manual Customer",
            "email": "manual@example.com",
            "password": "manual-registration-password",
            "confirm_password": "manual-registration-password",
            "submit": "Create",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/register/complete")

    with app.app_context():
        customer = db.session.scalar(db.select(Client).where(Client.login == "manual-customer"))
        assert customer is not None
        assert customer.name == "manual-customer"
        assert customer.email == "manual@example.com"
        assert customer.check_password("manual-registration-password")


def test_manual_registration_rejects_duplicate_login(app, client, customer_records):
    app.config["WTF_CSRF_ENABLED"] = False

    response = client.post(
        "/register",
        data={
            "login": "customer-one",
            "name": "Duplicate",
            "email": "different@example.com",
            "password": "manual-registration-password",
            "confirm_password": "manual-registration-password",
        },
    )

    assert response.status_code == 200
    assert "Этот логин уже используется".encode() in response.data


def test_automatic_registration_uses_primary_system_profile(app, client):
    app.config["WTF_CSRF_ENABLED"] = False

    response = client.post(
        "/register?token=DEMO-TOKEN-1001",
        data={
            "login": "linked-customer",
            "name": "Linked Customer",
            "email": "linked@example.com",
            "password": "linked-registration-password",
            "confirm_password": "linked-registration-password",
        },
    )

    assert response.status_code == 302
    with app.app_context():
        customer = db.session.scalar(db.select(Client).where(Client.login == "linked-customer"))
        assert customer is not None
        assert customer.external_id == "DEMO-1001"
        assert customer.email == "linked@example.com"


def test_registration_rejects_unknown_primary_system_token(app, client):
    app.config["WTF_CSRF_ENABLED"] = False

    response = client.get("/register?token=unknown-token")

    assert response.status_code == 400
