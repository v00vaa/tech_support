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
    find_blocked_entries,
    import_entries,
    parse_import_content,
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


def test_parse_txt_import_uses_selected_kind() -> None:
    records = parse_import_content(" spam \nspam\nphrase", "txt", INVALID_EXAMPLE)
    assert records == [
        (INVALID_EXAMPLE, "spam", None, True, "WHOLE_WORD"),
        (INVALID_EXAMPLE, "phrase", None, True, "WHOLE_WORD"),
    ]


def test_parse_csv_import_preserves_category_and_state() -> None:
    content = (
        "kind,value,category,is_active\n"
        "BLOCKED_TERM,spam,abuse,false\n"
        "INVALID_EXAMPLE,offensive text,,true\n"
    )
    assert parse_import_content(content, "csv") == [
        (BLOCKED_TERM, "spam", "abuse", False, "SUBSTRING"),
        (INVALID_EXAMPLE, "offensive text", None, True, "WHOLE_WORD"),
    ]


def test_parse_csv_rejects_unknown_kind_and_invalid_boolean() -> None:
    with pytest.raises(ValueError):
        parse_import_content("kind,value\nUNKNOWN,spam\n", "csv")
    with pytest.raises(ValueError):
        parse_import_content("kind,value,is_active\nBLOCKED_TERM,spam,maybe\n", "csv")


def test_import_entries_skips_duplicates_without_overwriting(database, app) -> None:
    with app.app_context():
        add_entries(BLOCKED_TERM, "spam")
        db.session.commit()
        added, duplicates = import_entries(
            [
                (BLOCKED_TERM, "SPAM", "other", False, "WHOLE_WORD"),
                (INVALID_EXAMPLE, "invalid sample", "abuse", False, "WHOLE_WORD"),
            ]
        )
        db.session.commit()
        assert (added, duplicates) == (1, 1)
        entry = db.session.scalar(
            db.select(ModerationEntry).where(ModerationEntry.kind == INVALID_EXAMPLE)
        )
        assert entry is not None
        assert entry.category == "abuse"
        assert entry.is_active is False


def test_parse_import_rejects_oversized_record_count() -> None:
    content = "\n".join(f"term-{index}" for index in range(10001))
    with pytest.raises(ValueError):
        parse_import_content(content, "txt")



def test_blocked_term_match_strategies() -> None:
    whole_word = ModerationEntry(
        kind=BLOCKED_TERM,
        value="spam",
        normalized_value="x",
        match_type="WHOLE_WORD",
    )
    substring = ModerationEntry(
        kind=BLOCKED_TERM,
        value="spam",
        normalized_value="y",
        match_type="SUBSTRING",
    )
    exact = ModerationEntry(
        kind=BLOCKED_TERM,
        value="spam now",
        normalized_value="z",
        match_type="EXACT",
    )
    assert find_blocked_entries("a spam message", [whole_word]) == [whole_word]
    assert find_blocked_entries("spammer", [whole_word]) == []
    assert find_blocked_entries("spammer", [substring]) == [substring]
    assert find_blocked_entries("  SPAM   NOW ", [exact]) == [exact]
    assert find_blocked_entries("please spam now", [exact]) == []



def test_csv_import_reads_match_type() -> None:
    content = "kind,value,match_type\\nBLOCKED_TERM,spam,SUBSTRING\\n"
    assert parse_import_content(content, "csv") == [
        (BLOCKED_TERM, "spam", None, True, "SUBSTRING")
    ]
