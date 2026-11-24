"""Moderation journal access and review tests."""

from collections.abc import Iterator

import pytest
from flask import Flask

from app.extensions import db
from app.models import Client, Employee, ModerationEvent, Permission, Role


@pytest.fixture
def moderation_review_records(app: Flask) -> Iterator[int]:
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.create_all()
        client = Client(name="Moderation Customer", login="moderation-customer")
        client.set_password("customer-password")
        employee = Employee(
            name="Moderation Reviewer",
            email="reviewer@example.com",
            position="Reviewer",
            password_hash="",
        )
        employee.set_password("reviewer-password")
        role = Role(code="moderation_reviewer", name="Moderation reviewer")
        role.permissions = [
            Permission(
                code="settings.view",
                name="View settings",
                category="settings",
            ),
            Permission(
                code="settings.edit",
                name="Edit settings",
                category="settings",
            ),
        ]
        employee.roles.append(role)
        db.session.add_all([client, employee])
        db.session.flush()
        event = ModerationEvent(
            client_id=client.id,
            source="classifier",
            message_text="Example rejected text",
            reason="Некорректное сообщение",
            category="abuse",
            confidence=0.95,
        )
        db.session.add(event)
        db.session.commit()
        event_id = event.id
        yield event_id
        db.session.remove()
        db.drop_all()


def test_employee_with_settings_permission_can_review_moderation_event(
    client, app: Flask, moderation_review_records: int
) -> None:
    response = client.post(
        "/login",
        data={"email": "reviewer@example.com", "password": "reviewer-password"},
    )
    assert response.status_code == 302

    journal_response = client.get("/settings/moderation/events")
    assert journal_response.status_code == 200
    assert b"Example rejected text" in journal_response.data

    review_response = client.post(
        f"/settings/moderation/events/{moderation_review_records}/review",
        data={"review_status": "IGNORED", "review_note": "Ложное срабатывание"},
    )
    assert review_response.status_code == 302

    with app.app_context():
        event = db.session.get(ModerationEvent, moderation_review_records)
        assert event is not None
        assert event.review_status == "IGNORED"
        assert event.review_note == "Ложное срабатывание"
        assert event.reviewed_by_employee_id is not None
        assert event.reviewed_at is not None


def test_employee_without_settings_edit_cannot_review_event(
    client, app: Flask, moderation_review_records: int
) -> None:
    with app.app_context():
        role = db.session.scalar(db.select(Role).where(Role.code == "moderation_reviewer"))
        assert role is not None
        role.permissions = [
            permission for permission in role.permissions if permission.code != "settings.edit"
        ]
        db.session.commit()

    client.post(
        "/login",
        data={"email": "reviewer@example.com", "password": "reviewer-password"},
    )
    response = client.post(
        f"/settings/moderation/events/{moderation_review_records}/review",
        data={"review_status": "REVIEWED", "review_note": ""},
    )

    assert response.status_code == 403



def test_moderation_journal_filters_by_decision(
    client, app: Flask, moderation_review_records: int
) -> None:
    with app.app_context():
        db.session.add(
            ModerationEvent(
                source="blocked_words",
                message_text="",
                reason="No violation",
                decision="ACCEPTED",
            )
        )
        db.session.commit()
    client.post(
        "/login",
        data={"email": "reviewer@example.com", "password": "reviewer-password"},
    )
    response = client.get("/settings/moderation/events?decision=ACCEPTED")
    assert response.status_code == 200
    assert "Найдено записей: 1".encode("utf-8") in response.data
    assert b"Example rejected text" not in response.data
