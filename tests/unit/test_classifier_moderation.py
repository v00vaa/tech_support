"""Tests for confidence-based moderation decisions."""

from app.models.general_settings import GeneralSettings
from app.web.routes import _moderate_customer_message


def _settings(threshold: float) -> GeneralSettings:
    return GeneralSettings(
        id=1,
        blocked_words_enabled=False,
        classifier_enabled=True,
        ollama_enabled=True,
        classifier_min_confidence=threshold,
    )


def test_classifier_rejects_message_at_or_above_confidence_threshold(
    app, monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.web.routes.classify_message",
        lambda message, settings: {
            "is_invalid": True,
            "category": "abuse",
            "reason": "Некорректное сообщение",
            "confidence": 0.85,
        },
    )

    with app.app_context():
        result = _moderate_customer_message("message", _settings(0.85))

    assert result == (
        "Некорректное сообщение",
        False,
        "abuse",
        0.85,
        "classifier",
    )


def test_classifier_does_not_reject_message_below_confidence_threshold(
    app, monkeypatch
) -> None:
    monkeypatch.setattr(
        "app.web.routes.classify_message",
        lambda message, settings: {
            "is_invalid": True,
            "category": "abuse",
            "reason": "Некорректное сообщение",
            "confidence": 0.74,
        },
    )

    with app.app_context():
        result = _moderate_customer_message("message", _settings(0.75))

    assert result == (None, False, None, None, None)


def test_zero_confidence_threshold_is_supported(app, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.web.routes.classify_message",
        lambda message, settings: {
            "is_invalid": True,
            "category": "abuse",
            "reason": "Некорректное сообщение",
            "confidence": 0.0,
        },
    )

    with app.app_context():
        result = _moderate_customer_message("message", _settings(0.0))

    assert result[0] == "Некорректное сообщение"
