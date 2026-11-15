"""Customer authentication and portal isolation tests."""

from collections.abc import Iterator

import pytest
from flask import Flask

from app.extensions import db
from app.models import AuthorType, Client, Dialog, Employee, Message


@pytest.fixture
def customer_records(app: Flask) -> Iterator[tuple[int, int, int]]:
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
        own_dialog = Dialog(client_id=customer.id, subject="My request", channel="Web")
        db.session.add(own_dialog)
        db.session.flush()
        db.session.add_all(
            [
                Message(
                    dialog_id=dialog.id,
                    author_type=AuthorType.EMPLOYEE,
                    author_id=None,
                    text="OTHER-CUSTOMER-INTERNAL-CONTENT",
                    is_internal=True,
                ),
                Message(
                    dialog_id=own_dialog.id,
                    author_type=AuthorType.EMPLOYEE,
                    author_id=None,
                    text="PUBLIC-ANSWER",
                    is_internal=False,
                ),
                Message(
                    dialog_id=own_dialog.id,
                    author_type=AuthorType.EMPLOYEE,
                    author_id=None,
                    text="INTERNAL-ONLY-CONTENT",
                    is_internal=True,
                ),
            ]
        )
        db.session.commit()
        ids = (customer.id, dialog.id, own_dialog.id)
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
    _, other_dialog_id, _ = customer_records
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
    assert "Неверный логин или пароль".encode() in response.data


def test_employee_cannot_open_customer_portal(client, customer_records) -> None:
    response = client.post(
        "/login",
        data={"email": "employee@example.com", "password": "employee-password"},
    )

    assert response.status_code == 302
    assert client.get("/portal/").status_code == 403


def test_customer_sees_public_messages_but_not_internal_notes(client, customer_records) -> None:
    _, _, own_dialog_id = customer_records
    client.post(
        "/client/login",
        data={"login": "customer-one", "password": "correct-horse-battery"},
    )

    response = client.get(f"/portal/dialogs/{own_dialog_id}")

    assert response.status_code == 200
    assert b"PUBLIC-ANSWER" in response.data
    assert b"INTERNAL-ONLY-CONTENT" not in response.data


def test_customer_can_create_a_support_dialog(client, customer_records, app) -> None:
    client.post(
        "/client/login",
        data={"login": "customer-one", "password": "correct-horse-battery"},
    )
    response = client.post(
        "/portal/dialogs/new",
        data={"subject": "New request", "message": "Please help"},
    )

    assert response.status_code == 302
    with app.app_context():
        dialog = db.session.scalar(db.select(Dialog).where(Dialog.subject == "New request"))
        assert dialog is not None
        assert dialog.channel == "Web"


def test_customer_can_reply_to_own_dialog(client, customer_records, app) -> None:
    _, _, own_dialog_id = customer_records
    client.post(
        "/client/login",
        data={"login": "customer-one", "password": "correct-horse-battery"},
    )
    response = client.post(
        f"/portal/dialogs/{own_dialog_id}",
        data={"text": "Additional details"},
    )

    assert response.status_code == 302
    with app.app_context():
        message = db.session.scalar(db.select(Message).where(Message.text == "Additional details"))
        assert message is not None
        assert message.author_type == AuthorType.CLIENT
        assert message.is_internal is False


def test_employee_and_customer_session_ids_are_namespaced() -> None:
    customer = Client(id=7, name="Customer", login="customer")
    employee = Employee(
        id=7,
        name="Employee",
        email="employee@example.com",
        position="Support",
        password_hash="hash",
    )

    assert customer.get_id() == "client:7"
    assert employee.get_id() == "employee:7"
