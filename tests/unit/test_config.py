"""Tests for environment-backed settings."""

import pytest

from app.core.config import Settings, get_settings


def test_settings_read_prefixed_environment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SUPPORT_DEBUG", "true")
    monkeypatch.setenv("SUPPORT_DATABASE_ECHO", "true")

    settings = Settings()

    assert settings.debug is True
    assert settings.database_echo is True


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()

    assert get_settings() is get_settings()


def test_production_rejects_debug_mode() -> None:
    with pytest.raises(ValueError, match="cannot be enabled"):
        Settings(environment="production", debug=True)
