"""Message classification orchestration built on the configured Ollama model."""

from typing import TypedDict

from app.models.general_settings import GeneralSettings
from app.services.moderation_service import INVALID_EXAMPLE, get_active_entries
from app.services.ollama_client import OllamaClient


class MessageClassification(TypedDict):
    """Validated result returned by the configured text classifier."""

    is_invalid: bool
    category: str
    reason: str
    confidence: float


def classify_message(message: str, settings: GeneralSettings) -> MessageClassification:
    """Classify a message using the configured local Ollama model."""
    client = OllamaClient(settings.ollama_base_url, settings.ollama_model)
    result = client.classify_message(
        message=message,
        invalid_examples=get_active_entries(INVALID_EXAMPLE),
        system_prompt=settings.ollama_system_prompt,
        classification_prompt=settings.ollama_classification_prompt,
    )
    if not isinstance(result.get("is_invalid"), bool):
        raise ValueError("Классификатор вернул некорректный признак is_invalid.")
    confidence = result.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("Классификатор вернул некорректную уверенность.")
    if not 0 <= confidence <= 1:
        raise ValueError("Уверенность классификатора должна быть в диапазоне от 0 до 1.")
    category = result.get("category", "")
    reason = result.get("reason", "")
    if not isinstance(category, str) or not isinstance(reason, str):
        raise ValueError("Классификатор вернул некорректные category или reason.")
    return {
        "is_invalid": result["is_invalid"],
        "category": category[:120],
        "reason": reason[:1000],
        "confidence": float(confidence),
    }
