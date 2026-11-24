"""Deterministic moderation helpers for customer messages."""

import csv
import hashlib
import io
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
    normalized = " ".join(value.split()).strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


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
        db.session.add(
            ModerationEntry(kind=kind, value=value, normalized_value=normalized, is_active=True)
        )
        existing.add(normalized)
        added += 1
    return added, duplicates



def parse_import_content(
    content: str,
    file_format: str,
    default_kind: str = BLOCKED_TERM,
) -> list[tuple[str, str, str | None, bool]]:
    """Parse CSV/TXT import data into validated moderation records."""
    if default_kind not in {BLOCKED_TERM, INVALID_EXAMPLE}:
        raise ValueError("Неизвестный тип записей модерации.")
    records: list[tuple[str, str, str | None, bool]] = []
    if file_format == "txt":
        records.extend((default_kind, value, None, True) for value in normalize_entries(content))
    elif file_format == "csv":
        reader = csv.DictReader(io.StringIO(content))
        required = {"kind", "value"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("CSV должен содержать столбцы kind и value.")
        for row in reader:
            kind = (row.get("kind") or "").strip()
            value = " ".join((row.get("value") or "").split()).strip()
            category = (row.get("category") or "").strip() or None
            active_raw = (row.get("is_active") or "true").strip().casefold()
            if kind not in {BLOCKED_TERM, INVALID_EXAMPLE}:
                raise ValueError("CSV содержит неизвестный тип записи.")
            if not value:
                continue
            if category and len(category) > 80:
                raise ValueError("Категория не должна превышать 80 символов.")
            if active_raw not in {"true", "false", "1", "0", "yes", "no"}:
                raise ValueError("Поле is_active должно содержать true или false.")
            records.append((kind, value, category, active_raw in {"true", "1", "yes"}))
    else:
        raise ValueError("Поддерживаются только файлы CSV и TXT.")
    if len(records) > 10000:
        raise ValueError("Файл не должен содержать более 10000 записей.")
    return records


def import_entries(
    records: list[tuple[str, str, str | None, bool]],
) -> tuple[int, int]:
    """Import validated records, skipping duplicates without overwriting existing ones."""
    existing = {
        (kind, normalized)
        for kind, normalized in db.session.execute(
            select(ModerationEntry.kind, ModerationEntry.normalized_value)
        ).all()
    }
    added = duplicates = 0
    for kind, value, category, is_active in records:
        if kind not in {BLOCKED_TERM, INVALID_EXAMPLE}:
            raise ValueError("Неизвестный тип записи модерации.")
        normalized = normalize_entry(value)
        normalized_value = " ".join(value.split()).strip()
        if not normalized_value or (kind, normalized) in existing:
            duplicates += 1
            continue
        db.session.add(
            ModerationEntry(
                kind=kind,
                value=normalized_value,
                normalized_value=normalized,
                category=category,
                is_active=is_active,
            )
        )
        existing.add((kind, normalized))
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
