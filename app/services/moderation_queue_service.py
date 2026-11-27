"""Background moderation queue for unclaimed first-line customer messages."""

from datetime import UTC, datetime, timedelta

from flask import current_app
from sqlalchemy import and_, or_, select

from app.extensions import db
from app.models import Dialog, DialogStatus, GeneralSettings, Message, ModerationEvent
from app.services.classifier_service import classify_message
from app.services.ollama_client import OllamaError

PENDING = "PENDING"
PROCESSING = "PROCESSING"
ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"
BYPASSED = "BYPASSED"
_RETRY_AFTER = timedelta(minutes=2)


def _still_in_first_line_queue(dialog: Dialog) -> bool:
    role = dialog.assigned_role
    return bool(
        dialog.responsible_employee_id is None
        and dialog.status in {DialogStatus.OPEN, DialogStatus.WAITING_EMPLOYEE}
        and role is not None
        and role.is_active
        and role.is_first_line
        and role.role_type == "MAIN"
        and role.scope_role_id is None
        and role.code != "administrator"
    )


def _finish_message(
    message: Message,
    *,
    decision: str,
    reason: str,
    source: str,
    category: str | None = None,
    confidence: float | None = None,
    model_name: str | None = None,
) -> None:
    message.moderation_status = decision
    message.moderation_reason = reason
    message.moderation_started_at = None
    dialog = message.dialog
    dialog.updated_at = datetime.now(UTC)
    db.session.add(
        ModerationEvent(
            client_id=dialog.client_id,
            dialog_id=dialog.id,
            message_id=message.id,
            source=source,
            message_text=message.text if decision == REJECTED else "",
            decision=decision,
            category=category,
            model_name=model_name,
            reason=reason,
            confidence=confidence,
        )
    )
    db.session.commit()


def process_pending_moderation(*, limit: int = 5) -> int:
    """Claim pending rows safely, call Ollama outside the transaction, and persist decisions.

    A PROCESSING row older than two minutes is reclaimed after a worker crash.
    Classification errors fail open, preserving the existing non-blocking policy.
    """
    if limit < 1:
        raise ValueError("Лимит обработки модерации должен быть положительным.")

    processed = 0
    for _ in range(limit):
        now = datetime.now(UTC)
        retry_before = now - _RETRY_AFTER
        candidate = db.session.scalar(
            select(Message)
            .where(
                or_(
                    Message.moderation_status == PENDING,
                    and_(
                        Message.moderation_status == PROCESSING,
                        Message.moderation_started_at.is_not(None),
                        Message.moderation_started_at <= retry_before,
                    ),
                ),
                Message.deleted_at.is_(None),
            )
            .order_by(Message.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if candidate is None:
            db.session.rollback()
            break

        message_id = candidate.id
        candidate.moderation_status = PROCESSING
        candidate.moderation_started_at = now
        db.session.commit()

        message = db.session.get(Message, message_id)
        if message is None or message.deleted_at is not None:
            db.session.rollback()
            continue
        dialog = db.session.get(Dialog, message.dialog_id)
        settings = db.session.get(GeneralSettings, 1)
        if dialog is None:
            db.session.rollback()
            continue

        if not _still_in_first_line_queue(dialog):
            _finish_message(
                message,
                decision=BYPASSED,
                reason="Обращение уже вышло из очереди первого уровня; сообщение принято.",
                source="workflow",
            )
            processed += 1
            continue

        if settings is None or not settings.classifier_enabled or not settings.ollama_enabled:
            _finish_message(
                message,
                decision=BYPASSED,
                reason="AI-проверка отключена; сообщение принято.",
                source="workflow",
                model_name=settings.ollama_model if settings else None,
            )
            processed += 1
            continue

        try:
            result = classify_message(message.text, settings)
            invalid = result["is_invalid"]
            confidence = result["confidence"]
            rejected = invalid and confidence >= settings.classifier_min_confidence
            reason = (
                result["reason"].strip()
                or (
                    "Уточните суть обращения, ожидаемый результат и уже выполненные действия. "
                    "Если часть сведений недоступна, объясните почему и опишите, что известно."
                )
            ) if rejected else (
                "Классификатор отметил сообщение, но уверенность ниже порога."
                if invalid
                else "Классификатор не обнаружил нарушений."
            )
            category = result["category"][:80] or None
        except (OllamaError, ValueError):
            current_app.logger.exception(
                "Background moderation failed for message %s; allowing delivery", message_id
            )
            rejected = False
            reason = "Классификатор временно недоступен; сообщение принято без AI-проверки."
            confidence = None
            category = None
        except Exception:
            db.session.rollback()
            current_app.logger.exception(
                "Unexpected background moderation error for message %s", message_id
            )
            continue

        # A concurrent handoff during the HTTP call must override the classifier result.
        db.session.refresh(message)
        dialog = db.session.get(Dialog, message.dialog_id)
        if dialog is None:
            db.session.rollback()
            continue
        db.session.refresh(dialog)
        if not _still_in_first_line_queue(dialog):
            decision = BYPASSED
            source = "workflow"
            reason = "Обращение передано или взято в работу; сообщение принято без блокировки."
            confidence = None
            category = None
        else:
            decision = REJECTED if rejected else ACCEPTED
            source = "classifier"
        try:
            _finish_message(
                message,
                decision=decision,
                reason=reason,
                source=source,
                category=category,
                confidence=confidence,
                model_name=settings.ollama_model,
            )
        except Exception:
            db.session.rollback()
            current_app.logger.exception(
                "Could not persist moderation decision for message %s", message_id
            )
            continue
        processed += 1

    return processed
