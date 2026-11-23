"""Small synchronous client for the Ollama HTTP API."""

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OllamaError(RuntimeError):
    """Raised when Ollama cannot be reached or returns an invalid response."""


class OllamaClient:
    """Client for Ollama's /api/tags and /api/chat endpoints."""

    def __init__(self, base_url: str, model: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def _request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="GET" if payload is None else "POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise OllamaError(f"Ошибка запроса Ollama: {error}") from error
        if not isinstance(result, dict):
            raise OllamaError("Ollama вернула ответ неожиданного формата.")
        return result

    def list_models(self) -> list[str]:
        """Return model names available in the Ollama instance."""
        result = self._request("/api/tags")
        models = result.get("models", [])
        if not isinstance(models, list):
            raise OllamaError("Ollama вернула некорректный список моделей.")
        return [
            str(item["name"])
            for item in models
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]

    def classify_message(
        self,
        message: str,
        invalid_examples: list[str],
        system_prompt: str,
        classification_prompt: str,
    ) -> dict[str, Any]:
        """Classify a message and parse the model's JSON response."""
        prompt = classification_prompt.replace(
            "{invalid_examples}", "\\n".join(invalid_examples)
        ).replace("{message}", message)
        result = self._request(
            "/api/chat",
            {
                "model": self.model,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        response = result.get("message")
        content = response.get("content") if isinstance(response, dict) else None
        if not isinstance(content, str):
            raise OllamaError("Ollama не вернула текст классификации.")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            raise OllamaError("Ollama вернула некорректный JSON классификации.") from error
        if not isinstance(parsed, dict) or not isinstance(parsed.get("is_invalid"), bool):
            raise OllamaError("Ответ классификатора не содержит boolean is_invalid.")
        return parsed
