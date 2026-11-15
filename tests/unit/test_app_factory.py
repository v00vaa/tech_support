"""Tests for application composition."""

from flask import Flask

from app import create_app
from app.core.config import Settings


def test_create_app_registers_transport_and_database() -> None:
    app = create_app(
        Settings(
            database_url="sqlite+pysqlite:///:memory:",
            environment="testing",
        )
    )

    try:
        assert isinstance(app, Flask)
        assert "sqlalchemy" in app.extensions
        assert "database" in app.extensions
        assert "api.liveness" in app.view_functions
    finally:
        with app.app_context():
            app.extensions["database"].engine.dispose()



def test_client_account_is_blocked_from_employee_routes(app) -> None:
    from app.extensions import db
    from app.models import Client

    with app.app_context():
        db.create_all()
        customer = Client(
            name="Boundary Customer",
            login="boundary-customer",
            email="boundary@example.com",
        )
        customer.set_password("boundary-customer-password")
        db.session.add(customer)
        db.session.commit()
        customer_id = customer.id

    test_client = app.test_client()
    with test_client.session_transaction() as session:
        session["_user_id"] = f"client:{customer_id}"
        session["_fresh"] = True

    assert test_client.get("/clients").status_code == 403


def test_employee_must_change_password_is_redirected_from_protected_pages(app) -> None:
    from app.extensions import db
    from app.models import Employee

    with app.app_context():
        db.create_all()
        employee = Employee(
            name="Password Change Employee",
            email="must-change@example.com",
            position="Support",
            password_hash="",
            must_change_password=True,
        )
        employee.set_password("employee-password")
        db.session.add(employee)
        db.session.commit()
        employee_id = employee.id

    test_client = app.test_client()
    with test_client.session_transaction() as session:
        session["_user_id"] = f"employee:{employee_id}"
        session["_fresh"] = True

    response = test_client.get("/clients")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/change-password")

    allowed = test_client.get("/change-password")
    assert allowed.status_code == 200


def test_user_loader_supports_legacy_employee_ids_and_rejects_invalid_ids(app) -> None:
    from app import load_user
    from app.extensions import db
    from app.models import Employee

    with app.app_context():
        db.create_all()
        employee = Employee(
            name="Legacy Session Employee",
            email="legacy-session@example.com",
            position="Support",
            password_hash="",
        )
        employee.set_password("employee-password")
        db.session.add(employee)
        db.session.commit()

        assert load_user(str(employee.id)) is employee
        assert load_user(f"employee:{employee.id}") is employee
        assert load_user("client:not-an-id") is None
        assert load_user("unknown:1") is None
        assert load_user("invalid") is None
