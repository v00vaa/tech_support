"""Tests for the main-system registration adapters."""

import json
from io import BytesIO
from unittest.mock import patch
from urllib.request import Request

import pytest

from app.services.registration_provider import (
    HttpRegistrationProvider,
    MockRegistrationProvider,
    RegistrationTokenInvalid,
)


def test_mock_provider_returns_demo_profile() -> None:
    profile = MockRegistrationProvider().get_profile("DEMO-TOKEN-1001")
    assert profile.external_id == "DEMO-1001"
    assert profile.name == "Демонстрационный клиент"


def test_mock_provider_rejects_unknown_token() -> None:
    with pytest.raises(RegistrationTokenInvalid):
        MockRegistrationProvider().get_profile("unknown")


def test_http_provider_sends_both_credentials_and_parses_profile() -> None:
    response = BytesIO(json.dumps({
        "external_id": "customer-42", "name": "Test", "email": None, "phone": "+100"
    }).encode())
    provider = HttpRegistrationProvider(
        base_url="https://main.example.com",
        service_token="service-secret",
        profile_path="/api/v1/profile",
        redeem_path="/api/v1/redeem",
        timeout=3,
    )
    with patch("app.services.registration_provider.urlopen", return_value=response) as opener:
        profile = provider.get_profile("one-time-token")
    request = opener.call_args.args[0]
    assert isinstance(request, Request)
    assert request.get_method() == "GET"
    assert request.get_header("Authorization") == "Bearer service-secret"
    assert request.get_header("X-registration-token") == "one-time-token"
    assert profile.external_id == "customer-42"


def test_http_provider_redeems_with_idempotency_key_and_accepts_empty_body() -> None:
    response = BytesIO(b"")
    provider = HttpRegistrationProvider(
        base_url="https://main.example.com",
        service_token="service-secret",
        profile_path="/profile",
        redeem_path="/redeem",
        timeout=3,
    )
    with patch("app.services.registration_provider.urlopen", return_value=response) as opener:
        provider.redeem_token("one-time-token", idempotency_key="support-client-42")
    request = opener.call_args.args[0]
    assert request.get_method() == "POST"
    assert request.get_header("Idempotency-key") == "support-client-42"
    assert request.data == b"{}"