"""Deterministic moderation helpers for customer messages."""

import re

from sqlalchemy import select

from app.extensions import db
from app.models.moderation_entry import ModerationEntry

BLOCKED_TERM = "BLOCKED_TERM"
INVALID_EXAMPLE = "INVALID_EXAMPLE"


def normalize_entries(raw_value: str) -> list[str]:
    """Split multiline input into unique, trimmed entries."""
    entries: list[str] = []
    seen: set[str] = set()
    for raw_entry in raw_value.splitlines():
        entry = " ".join(raw_entry.split()).strip()
        key = entry.casefold()
        if entry and key not in seen:
            seen.add(key)
            entries.append(entry)
    return entries


def normalize_entry(value: str) -> str:
    """Normalize one value for case-insensitive uniqueness."""
    return " ".join(value.split()).strip().casefold()


def get_active_entries(kind: str) -> list[str]:
    """Return active entries of one moderation kind."""
    return list(
        db.session.scalars(
            select(ModerationEntry.value)
            .where(ModerationEntry.kind == kind, ModerationEntry.is_active.is_(True))
            .order_by(ModerationEntry.id)
        ).all()
    )


def add_entries(kind: str, raw_value: str) -> tuple[int, int]:
    """Add unique multiline entries and return added and duplicate counts."""
    if kind not in {BLOCKED_TERM, INVALID_EXAMPLE}:
        raise ValueError("Неизвестный тип записи модерации.")
    existing = set(
        db.session.scalars(
            select(ModerationEntry.normalized_value).where(ModerationEntry.kind == kind)
        ).all()
    )
    added = duplicates = 0
    for value in normalize_entries(raw_value):
        normalized = normalize_entry(value)
        if normalized in existing:
            duplicates += 1
            continue
        if len(normalized) > 1000:
            raise ValueError("Нормализованная запись не должна превышать 1000 символов.")
        db.session.add(
            ModerationEntry(kind=kind, value=value, normalized_value=normalized, is_active=True)
        )
        existing.add(normalized)
        added += 1
    return added, duplicates


def find_blocked_terms(message: str, entries: list[str]) -> list[str]:
    """Return blocked terms found as whole words/phrases, case-insensitively."""
    matches: list[str] = []
    for entry in entries:
        words = entry.split()
        if not words:
            continue
        pattern = r"(?<!\w)" + r"\s+".join(re.escape(word) for word in words) + r"(?!\w)"
        if re.search(pattern, message, flags=re.IGNORECASE | re.UNICODE):
            matches.append(entry)
    return matches


def check_message(message: str, blocked_words: str) -> list[str]:
    """Compatibility helper for newline-separated input."""
    return find_blocked_terms(message, normalize_entries(blocked_words))
