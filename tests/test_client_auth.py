"""Customer authentication and portal isolation tests."""

from collections.abc import Iterator

import pytest
from flask import Flask

from app.extensions import db
from app.models import AuthorType, Client, Dialog, Employee, Message


@pytest.fixture
def customer_records(app: Flask) -> Iterator[tuple[int, int]]:
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.create_all()
        customer = Client(name="Customer One", login="customer-one", email="one@example.com")
        customer.set_password("correct-horse-battery")
        other = Client(name="Customer Two", login="customer-two", email="two@example.com")
        other.set_password("another-correct-password")
        employee = Employee(
            name="Support Employee",
            email="employee@example.com",
            position="Support",
            password_hash="",
        )
        employee.set_password("employee-password")
        db.session.add_all([customer, other, employee])
        db.session.flush()

        dialog = Dialog(client_id=other.id, subject="Private request", channel="Web")
        db.session.add(dialog)
        db.session.flush()
        db.session.add(
            Message(
                dialog_id=dialog.id,
                author_type=AuthorType.EMPLOYEE,
                author_id=None,
                text="INTERNAL-ONLY-CONTENT",
                is_internal=True,
            )
        )
        db.session.commit()
        ids = (customer.id, dialog.id)
        yield ids
        db.session.remove()
        db.drop_all()


def test_customer_can_login_and_open_portal(client, customer_records) -> None:
    response = client.post(
        "/client/login",
        data={"login": "CUSTOMER-ONE", "password": "correct-horse-battery"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/portal/")

    portal_response = client.get("/portal/")
    assert portal_response.status_code == 200
    assert b"Customer One" in portal_response.data


def test_customer_cannot_open_staff_pages(client, customer_records) -> None:
    client.post(
        "/client/login",
        data={"login": "customer-one", "password": "correct-horse-battery"},
    )

    response = client.get("/clients")

    assert response.status_code == 403


def test_customer_cannot_read_another_customers_dialog(client, customer_records) -> None:
    _, other_dialog_id = customer_records
    client.post(
        "/client/login",
        data={"login": "customer-one", "password": "correct-horse-battery"},
    )

    response = client.get(f"/portal/dialogs/{other_dialog_id}")

    assert response.status_code == 404


def test_customer_login_rejects_invalid_password(client, customer_records) -> None:
    response = client.post(
        "/client/login",
        data={"login": "customer-one", "password": "wrong-password"},
    )

    assert response.status_code == 200
    assert b"Неверный логин или пароль" in response.data



def test_employee_cannot_open_customer_portal(client, customer_records) -> None:
    response = client.post(
        "/login",
        data={"email": "employee@example.com", "password": "employee-password"},
    )

    assert response.status_code == 302
    assert client.get("/portal/").status_code == 403
