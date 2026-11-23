"""Tests for the Ollama HTTP client and classifier validation."""

import json

import pytest

from app.models.general_settings import GeneralSettings
from app.services.classifier_service import classify_message
from app.services.ollama_client import OllamaClient, OllamaError


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_list_models_reads_ollama_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.ollama_client.urlopen",
        lambda request, timeout: FakeResponse({"models": [{"name": "qwen2.5:3b"}]}),
    )
    assert OllamaClient("http://ollama:11434", "qwen2.5:3b").list_models() == ["qwen2.5:3b"]


def test_classify_message_parses_structured_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.ollama_client.urlopen",
        lambda request, timeout: FakeResponse(
            {"message": {"content": '{"is_invalid": false, "category": "ok", "reason": "", "confidence": 0.9}'}}
        ),
    )
    result = OllamaClient("http://ollama:11434", "qwen2.5:3b").classify_message(
        "Здравствуйте",
        ["оскорбление"],
        "system",
        "Примеры: {invalid_examples}; текст: {message}",
    )
    assert result["is_invalid"] is False


def test_ollama_rejects_invalid_classifier_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.ollama_client.urlopen",
        lambda request, timeout: FakeResponse({"message": {"content": '{"invalid": true}'}}),
    )
    with pytest.raises(OllamaError):
        OllamaClient("http://ollama:11434", "qwen2.5:3b").classify_message(
            "message", [], "system", "{message}"
        )


def test_classifier_validates_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.classifier_service.OllamaClient.classify_message",
        lambda *args, **kwargs: {
            "is_invalid": True,
            "category": "abuse",
            "reason": "test",
            "confidence": 2,
        },
    )
    with pytest.raises(ValueError):
        classify_message("bad", GeneralSettings(id=1))
