"""Tests for normalized moderation dictionary entries."""

from collections.abc import Iterator

import pytest

from app.extensions import db
from app.models.moderation_entry import ModerationEntry
from app.services.moderation_service import (
    BLOCKED_TERM,
    INVALID_EXAMPLE,
    add_entries,
    get_active_entries,
)


@pytest.fixture
def database(app) -> Iterator[None]:
    with app.app_context():
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()


def test_add_entries_deduplicates_case_and_whitespace(database, app) -> None:
    with app.app_context():
        added, duplicates = add_entries(
            BLOCKED_TERM,
            "  Запрещённая   фраза  \nзапрещённая фраза\nСПАМ",
        )
        db.session.commit()
        assert (added, duplicates) == (2, 0)
        assert get_active_entries(BLOCKED_TERM) == ["Запрещённая фраза", "СПАМ"]


def test_existing_inactive_entry_is_not_duplicated(database, app) -> None:
    with app.app_context():
        add_entries(BLOCKED_TERM, "спам")
        db.session.commit()
        entry = db.session.scalar(db.select(ModerationEntry))
        assert entry is not None
        entry.is_active = False
        db.session.commit()

        added, duplicates = add_entries(BLOCKED_TERM, "СПАМ")
        db.session.commit()
        assert (added, duplicates) == (0, 1)
        assert get_active_entries(BLOCKED_TERM) == []


def test_classifier_examples_are_separate_from_blocked_terms(database, app) -> None:
    with app.app_context():
        add_entries(BLOCKED_TERM, "спам")
        add_entries(INVALID_EXAMPLE, "оскорбительное сообщение")
        db.session.commit()
        assert get_active_entries(BLOCKED_TERM) == ["спам"]
        assert get_active_entries(INVALID_EXAMPLE) == ["оскорбительное сообщение"]


def test_add_entries_rejects_unknown_kind(database, app) -> None:
    with app.app_context(), pytest.raises(ValueError):
        add_entries("UNKNOWN", "value")
