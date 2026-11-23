"""Deterministic moderation helpers for customer messages."""

import re


def normalize_entries(raw_value: str) -> list[str]:
    """Split newline-separated settings into unique, trimmed entries."""
    entries: list[str] = []
    seen: set[str] = set()
    for raw_entry in raw_value.splitlines():
        entry = " ".join(raw_entry.split()).strip()
        key = entry.casefold()
        if entry and key not in seen:
            seen.add(key)
            entries.append(entry)
    return entries


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
    """Check a message against a newline-separated blocked-word list."""
    return find_blocked_terms(message, normalize_entries(blocked_words))
