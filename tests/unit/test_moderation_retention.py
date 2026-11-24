"""Tests for the moderation journal retention policy."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func

from app.extensions import db
from app.models import GeneralSettings, ModerationEvent
from app.services.attachment_storage_service import cleanup_expired_moderation_events


@pytest.fixture
def moderation_database(app) -> Iterator[None]:
    with app.app_context():
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()


def test_moderation_journal_retention_defaults_to_never(moderation_database, app) -> None:
    with app.app_context():
        db.session.add(GeneralSettings(id=1))
        db.session.add(
            ModerationEvent(
                source="blocked_words",
                message_text="Retained message",
                reason="No matching rule",
                decision="ACCEPTED",
                created_at=datetime.now(UTC) - timedelta(days=400),
            )
        )
        db.session.commit()

        assert cleanup_expired_moderation_events() == 0
        assert db.session.scalar(db.select(func.count()).select_from(ModerationEvent)) == 1


def test_moderation_journal_cleanup_removes_only_expired_records(moderation_database, app) -> None:
    with app.app_context():
        db.session.add(GeneralSettings(id=1, moderation_event_retention_days=30))
        now = datetime.now(UTC)
        db.session.add_all(
            [
                ModerationEvent(
                    source="blocked_words",
                    message_text="Old message",
                    reason="Expired",
                    decision="REJECTED",
                    created_at=now - timedelta(days=31),
                ),
                ModerationEvent(
                    source="classifier",
                    message_text="Recent message",
                    reason="Retained",
                    decision="ACCEPTED",
                    created_at=now - timedelta(days=2),
                ),
            ]
        )
        db.session.commit()

        assert cleanup_expired_moderation_events(limit=10) == 1
        remaining = db.session.scalars(db.select(ModerationEvent)).all()
        assert [event.message_text for event in remaining] == ["Recent message"]


def test_moderation_journal_cleanup_respects_batch_limit(moderation_database, app) -> None:
    with app.app_context():
        db.session.add(GeneralSettings(id=1, moderation_event_retention_days=1))
        old_date = datetime.now(UTC) - timedelta(days=2)
        db.session.add_all(
            [
                ModerationEvent(
                    source="blocked_words",
                    message_text=f"Old {index}",
                    reason="Expired",
                    created_at=old_date,
                )
                for index in range(3)
            ]
        )
        db.session.commit()

        assert cleanup_expired_moderation_events(limit=2) == 2
        assert db.session.scalar(db.select(func.count()).select_from(ModerationEvent)) == 1
