"""Tests for forced initial password replacement."""

from app.extensions import db
from app.models import Employee


def test_forced_password_change_redirects_until_password_is_updated(app, client) -> None:  # type: ignore[no-untyped-def]
    with app.app_context():
        db.create_all()
        employee = Employee(
            name="Admin", email="admin@example.com", position="Admin",
            password_hash="", must_change_password=True,
        )
        employee.set_password("temporary-password")
        db.session.add(employee)
        db.session.commit()
        employee_id = employee.id

    with client:
        with client.session_transaction() as session:
            session["_user_id"] = str(employee_id)
            session["_fresh"] = True
        response = client.get("/")
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/change-password")
