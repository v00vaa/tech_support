"""Tests for deterministic message moderation helpers."""

from app.services.moderation_service import check_message, find_blocked_terms, normalize_entries


def test_normalize_entries_trims_and_deduplicates_case_insensitively() -> None:
    assert normalize_entries(" Спам  \nспам\n\nОскорбительная фраза ") == [
        "Спам",
        "Оскорбительная фраза",
    ]


def test_blocked_terms_match_whole_words_and_phrases_case_insensitively() -> None:
    assert check_message("Это СПАМ! И запрещённая   фраза.", "спам\nзапрещённая фраза") == [
        "спам",
        "запрещённая фраза",
    ]


def test_blocked_terms_do_not_match_inside_other_words() -> None:
    assert find_blocked_terms("спамить полезно", ["спам"]) == []
