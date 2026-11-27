"""Tests for the asynchronous Ollama moderation queue."""

from app.extensions import db
from app.models import (
    Client,
    Dialog,
    DialogStatus,
    Employee,
    GeneralSettings,
    Message,
    ModerationEvent,
    Role,
)
from app.services.dialog_service import claim_dialog
from app.services.moderation_queue_service import process_pending_moderation


def _create_pending_message(app):
    with app.app_context():
        db.create_all()
        role = Role(
            code="moderation_first_line",
            name="First line",
            is_first_line=True,
            is_active=True,
            role_type="MAIN",
        )
        client = Client(name="Queue customer", email="queue@example.com")
        employee = Employee(
            name="Queue employee",
            email="queue-employee@example.com",
            position="Support",
            password_hash="test-hash",
            is_active=True,
        )
        db.session.add_all([role, client, employee])
        db.session.flush()
        dialog = Dialog(
            client_id=client.id,
            assigned_role_id=role.id,
            subject="Moderation queue",
            channel="Web",
            status=DialogStatus.OPEN,
        )
        db.session.add(dialog)
        db.session.flush()
        message = Message(
            dialog_id=dialog.id,
            author_type="CLIENT",
            author_id=client.id,
            text="Please investigate this issue",
            is_internal=False,
            moderation_status="PENDING",
        )
        db.session.add_all(
            [
                message,
                GeneralSettings(
                    id=1,
                    blocked_words_enabled=False,
                    classifier_enabled=True,
                    ollama_enabled=True,
                    classifier_min_confidence=0.75,
                    ollama_model="qwen2.5:3b",
                ),
            ]
        )
        db.session.commit()
        return dialog.id, message.id, role.id, employee.id


def test_worker_accepts_message_and_releases_dialog_for_claim(
    app, monkeypatch
) -> None:
    dialog_id, message_id, role_id, employee_id = _create_pending_message(app)
    monkeypatch.setattr(
        "app.services.moderation_queue_service.classify_message",
        lambda message, settings: {
            "is_invalid": False,
            "category": "valid",
            "reason": "",
            "confidence": 0.98,
        },
    )

    with app.app_context():
        assert claim_dialog(dialog_id, employee_id, [role_id]) is False
        assert process_pending_moderation(limit=1) == 1
        message = db.session.get(Message, message_id)
        assert message is not None
        assert message.moderation_status == "ACCEPTED"
        assert message.moderation_reason == "Классификатор не обнаружил нарушений."
        event = db.session.scalar(
            db.select(ModerationEvent).where(ModerationEvent.message_id == message_id)
        )
        assert event is not None
        assert event.decision == "ACCEPTED"
        assert event.source == "classifier"
        assert claim_dialog(dialog_id, employee_id, [role_id]) is True


def test_worker_rejects_message_and_keeps_it_out_of_employee_queue(
    app, monkeypatch
) -> None:
    dialog_id, message_id, role_id, employee_id = _create_pending_message(app)
    monkeypatch.setattr(
        "app.services.moderation_queue_service.classify_message",
        lambda message, settings: {
            "is_invalid": True,
            "category": "missing_context",
            "reason": "Укажите, когда появилась ошибка.",
            "confidence": 0.99,
        },
    )

    with app.app_context():
        assert process_pending_moderation(limit=1) == 1
        message = db.session.get(Message, message_id)
        assert message is not None
        assert message.moderation_status == "REJECTED"
        assert message.moderation_reason == "Укажите, когда появилась ошибка."
        assert claim_dialog(dialog_id, employee_id, [role_id]) is False


def test_worker_bypasses_classifier_if_dialog_is_transferred_during_call(
    app, monkeypatch
) -> None:
    dialog_id, message_id, role_id, _ = _create_pending_message(app)
    with app.app_context():
        target = Role(
            code="moderation_second_line",
            name="Second line",
            is_active=True,
            role_type="MAIN",
        )
        db.session.add(target)
        db.session.commit()
        target_role_id = target.id

    def transfer_during_classification(message, settings):
        with app.app_context():
            dialog = db.session.get(Dialog, dialog_id)
            assert dialog is not None
            dialog.assigned_role_id = target_role_id
            db.session.commit()
        return {
            "is_invalid": True,
            "category": "invalid",
            "reason": "Should not block after handoff.",
            "confidence": 1.0,
        }

    monkeypatch.setattr(
        "app.services.moderation_queue_service.classify_message",
        transfer_during_classification,
    )
    with app.app_context():
        assert process_pending_moderation(limit=1) == 1
        message = db.session.get(Message, message_id)
        assert message is not None
        assert message.moderation_status == "BYPASSED"
        event = db.session.scalar(
            db.select(ModerationEvent).where(ModerationEvent.message_id == message_id)
        )
        assert event is not None
        assert event.decision == "BYPASSED"
        assert event.source == "workflow"
