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
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured.update(json.loads(request.data.decode("utf-8")))
        return FakeResponse(
            {
                "message": {
                    "content": json.dumps(
                        {
                            "is_invalid": False,
                            "category": "ok",
                            "reason": "",
                            "confidence": 0.9,
                        }
                    )
                }
            }
        )

    monkeypatch.setattr("app.services.ollama_client.urlopen", fake_urlopen)
    result = OllamaClient("http://ollama:11434", "qwen2.5:3b").classify_message(
        "Здравствуйте",
        ["оскорбление"],
        "system",
        "Примеры: {invalid_examples}; текст: {message}",
    )
    assert result["is_invalid"] is False
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert "оскорбление" in messages[0]["content"]
    assert "{message}" not in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "Здравствуйте"}


def test_ollama_rejects_invalid_classifier_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.ollama_client.urlopen",
        lambda request, timeout: FakeResponse({"message": {"content": '{"invalid": true}'}}),
    )
    with pytest.raises(OllamaError):
        OllamaClient("http://ollama:11434", "qwen2.5:3b").classify_message(
            "message", [], "system", "{message}"
        )


def test_ollama_rejects_out_of_range_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.ollama_client.urlopen",
        lambda request, timeout: FakeResponse(
            {
                "message": {
                    "content": json.dumps(
                        {
                            "is_invalid": True,
                            "category": "abuse",
                            "reason": "test",
                            "confidence": 1.5,
                        }
                    )
                }
            }
        ),
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



def test_generate_support_reply_returns_validated_customer_action(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured.update(json.loads(request.data.decode("utf-8")))
        return FakeResponse(
            {
                "message": {
                    "content": json.dumps(
                        {
                            "action": "NEED_INFO",
                            "reply": "Уточните, когда появилась ошибка. Если журнал недоступен, опишите последние действия.",
                        }
                    )
                }
            }
        )

    monkeypatch.setattr("app.services.ollama_client.urlopen", fake_urlopen)
    result = OllamaClient("http://ollama:11434", "qwen2.5:3b").generate_support_reply(
        message="Не работает вход",
        conversation_context="Клиент: Не работает вход",
        system_context="Вход выполняется по корпоративной учётной записи.",
        system_prompt="Ты помощник поддержки.",
    )

    assert result["action"] == "NEED_INFO"
    assert "журнал недоступен" in result["reply"]
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert "корпоративной учётной записи" in messages[0]["content"]
    assert "Клиент: Не работает вход" in messages[1]["content"]


def test_generate_support_reply_rejects_unknown_action(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.ollama_client.urlopen",
        lambda request, timeout: FakeResponse(
            {"message": {"content": '{"action": "DELETE_DIALOG", "reply": "done"}'}}
        ),
    )
    with pytest.raises(OllamaError):
        OllamaClient("http://ollama:11434", "qwen2.5:3b").generate_support_reply(
            "message", "history", "context", "system"
        )
