"""Customer authentication and portal isolation tests."""

from collections.abc import Iterator

import pytest
from flask import Flask

from app.extensions import db
from app.models import (
    AuthorType,
    Client,
    Dialog,
    Employee,
    GeneralSettings,
    Message,
    ModerationEntry,
    ModerationEvent,
    Role,
)

from app.services.moderation_service import normalize_entry


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
        first_line_role = Role(
            code="test_first_line",
            name="Test first-line support",
            is_first_line=True,
        )
        db.session.add_all([customer, other, employee, first_line_role])
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
        assert dialog.assigned_role_id is not None
        assert dialog.assigned_role.is_first_line is True
        assert dialog.role_assigned_at is not None


def test_customer_cannot_create_dialog_without_first_line_configuration(
    client, customer_records, app
) -> None:
    with app.app_context():
        role = db.session.scalar(db.select(Role).where(Role.code == "test_first_line"))
        assert role is not None
        role.is_first_line = False
        db.session.commit()

    client.post(
        "/client/login",
        data={"login": "customer-one", "password": "correct-horse-battery"},
    )
    response = client.post(
        "/portal/dialogs/new",
        data={"subject": "Unrouted request", "message": "Please help"},
    )

    assert response.status_code == 503
    with app.app_context():
        assert (
            db.session.scalar(db.select(Dialog).where(Dialog.subject == "Unrouted request")) is None
        )


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


def test_customer_cannot_create_dialog_with_blocked_words(client, customer_records, app) -> None:
    with app.app_context():
        db.session.add_all(
            [
                GeneralSettings(id=1, blocked_words_enabled=True),
                ModerationEntry(
                    kind="BLOCKED_TERM",
                    value="spam",
                    normalized_value=normalize_entry("spam"),
                ),
            ]
        )
        db.session.commit()

    client.post(
        "/client/login",
        data={"login": "customer-one", "password": "correct-horse-battery"},
    )
    response = client.post(
        "/portal/dialogs/new",
        data={"subject": "Blocked request", "message": "This is SPAM"},
    )

    assert response.status_code == 400
    with app.app_context():
        blocked_dialog = db.session.scalar(
            db.select(Dialog).where(Dialog.subject == "Blocked request")
        )
        assert blocked_dialog is None
        event = db.session.scalar(
            db.select(ModerationEvent).where(ModerationEvent.message_text == "This is SPAM")
        )
        assert event is not None
        assert event.client_id == customer_records[0]
        assert event.dialog_id is None
        assert event.source == "blocked_words"
        assert event.review_status == "NEW"


def test_customer_cannot_reply_with_blocked_words(client, customer_records, app) -> None:
    _, _, own_dialog_id = customer_records
    with app.app_context():
        db.session.add_all(
            [
                GeneralSettings(id=1, blocked_words_enabled=True),
                ModerationEntry(
                    kind="BLOCKED_TERM",
                    value="spam",
                    normalized_value=normalize_entry("spam"),
                ),
            ]
        )
        db.session.commit()

    client.post(
        "/client/login",
        data={"login": "customer-one", "password": "correct-horse-battery"},
    )
    response = client.post(
        f"/portal/dialogs/{own_dialog_id}",
        data={"text": "This is spam"},
    )

    assert response.status_code == 302
    with app.app_context():
        assert db.session.scalar(db.select(Message).where(Message.text == "This is spam")) is None
        event = db.session.scalar(
            db.select(ModerationEvent).where(ModerationEvent.message_text == "This is spam")
        )
        assert event is not None
        assert event.dialog_id == own_dialog_id


def test_customer_can_create_dialog_when_blocked_word_filter_is_disabled(
    client, customer_records, app
) -> None:
    with app.app_context():
        db.session.add(
            GeneralSettings(
                id=1,
                blocked_words="spam",
                blocked_words_enabled=False,
            )
        )
        db.session.commit()

    client.post(
        "/client/login",
        data={"login": "customer-one", "password": "correct-horse-battery"},
    )
    response = client.post(
        "/portal/dialogs/new",
        data={"subject": "Allowed while filter disabled", "message": "This is spam"},
    )

    assert response.status_code == 302
    with app.app_context():
        dialog = db.session.scalar(
            db.select(Dialog).where(Dialog.subject == "Allowed while filter disabled")
        )
        assert dialog is not None


def test_classifier_rejects_invalid_customer_message(
    client, customer_records, app, monkeypatch
) -> None:
    with app.app_context():
        db.session.add(
            GeneralSettings(
                id=1,
                classifier_enabled=True,
                ollama_enabled=True,
            )
        )
        db.session.commit()

    monkeypatch.setattr(
        "app.web.routes.classify_message",
        lambda message, settings: {
            "is_invalid": True,
            "category": "abuse",
            "reason": "Сообщение содержит оскорбления.",
            "confidence": 0.99,
        },
    )
    client.post(
        "/client/login",
        data={"login": "customer-one", "password": "correct-horse-battery"},
    )
    response = client.post(
        "/portal/dialogs/new",
        data={"subject": "Invalid request", "message": "Bad message"},
    )

    assert response.status_code == 400
    assert "Сообщение содержит оскорбления.".encode() in response.data
    with app.app_context():
        event = db.session.scalar(
            db.select(ModerationEvent).where(ModerationEvent.message_text == "Bad message")
        )
        assert event is not None
        assert event.source == "classifier"
        assert event.category == "abuse"
        assert event.confidence == 0.99
        rejected_dialog = db.session.scalar(
            db.select(Dialog).where(Dialog.subject == "Invalid request")
        )
        assert rejected_dialog is None


def test_classifier_is_not_called_when_ollama_is_disabled(
    client, customer_records, app, monkeypatch
) -> None:
    with app.app_context():
        db.session.add(
            GeneralSettings(
                id=1,
                classifier_enabled=True,
                ollama_enabled=False,
            )
        )
        db.session.commit()

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Ollama must stay disabled")

    monkeypatch.setattr("app.web.routes.classify_message", fail_if_called)
    client.post(
        "/client/login",
        data={"login": "customer-one", "password": "correct-horse-battery"},
    )
    response = client.post(
        "/portal/dialogs/new",
        data={"subject": "No model request", "message": "Normal message"},
    )

    assert response.status_code == 302


def test_customer_cannot_open_moderation_journal(client, customer_records) -> None:
    client.post(
        "/client/login",
        data={"login": "customer-one", "password": "correct-horse-battery"},
    )

    response = client.get("/settings/moderation/events")

    assert response.status_code == 403
