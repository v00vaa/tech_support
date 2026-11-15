"""Tests for the main-system registration adapters."""

import json
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError
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
    response = BytesIO(
        json.dumps(
            {"external_id": "customer-42", "name": "Test", "email": None, "phone": "+100"}
        ).encode()
    )
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
    assert request.unredirected_hdrs["X-registration-token"] == "one-time-token"
    assert request.unredirected_hdrs["Authorization"] == "Bearer service-secret"
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
    assert request.unredirected_hdrs["Idempotency-key"] == "support-client-42"
    assert request.unredirected_hdrs["X-registration-token"] == "one-time-token"
    assert request.data == b"{}"


def _http_provider() -> HttpRegistrationProvider:
    return HttpRegistrationProvider(
        base_url="https://main.example.com",
        service_token="service-secret",
        profile_path="/profile",
        redeem_path="/redeem",
        timeout=3,
    )


@pytest.mark.parametrize("status", [404, 410])
def test_http_provider_maps_missing_profile_to_invalid_token(status: int) -> None:
    error = HTTPError("https://main.example.com/profile", status, "missing", {}, None)
    with (
        patch("app.services.registration_provider.urlopen", side_effect=error),
        pytest.raises(RegistrationTokenInvalid),
    ):
        _http_provider().get_profile("expired-token")


def test_http_provider_maps_server_errors_to_provider_error() -> None:
    from app.services.registration_provider import RegistrationProviderError

    error = HTTPError("https://main.example.com/profile", 503, "unavailable", {}, None)
    with (
        patch("app.services.registration_provider.urlopen", side_effect=error),
        pytest.raises(RegistrationProviderError, match="HTTP 503"),
    ):
        _http_provider().get_profile("token")


@pytest.mark.parametrize("failure", [OSError("network down"), TimeoutError("timeout")])
def test_http_provider_maps_transport_errors(failure: Exception) -> None:
    from app.services.registration_provider import RegistrationProviderError

    with (
        patch("app.services.registration_provider.urlopen", side_effect=failure),
        pytest.raises(RegistrationProviderError, match="request failed"),
    ):
        _http_provider().get_profile("token")


@pytest.mark.parametrize("body", [b"not-json", b"[]", b'{"external_id": 123}'])
def test_http_provider_rejects_invalid_profile_responses(body: bytes) -> None:
    from app.services.registration_provider import RegistrationProviderError

    with (
        patch(
            "app.services.registration_provider.urlopen",
            return_value=BytesIO(body),
        ),
        pytest.raises(RegistrationProviderError),
    ):
        _http_provider().get_profile("token")


def test_http_provider_rejects_non_string_optional_profile_fields() -> None:
    from app.services.registration_provider import RegistrationProviderError

    response = BytesIO(b'{"external_id": "customer-1", "email": 42}')
    with (
        patch("app.services.registration_provider.urlopen", return_value=response),
        pytest.raises(RegistrationProviderError, match="schema is invalid"),
    ):
        _http_provider().get_profile("token")


def test_registration_provider_factory_supports_injection_and_modes(app) -> None:
    from app.services.registration_provider import (
        MockRegistrationProvider,
        RegistrationProviderError,
        get_registration_provider,
    )

    with app.app_context():
        app.config["REGISTRATION_PROVIDER_MODE"] = "mock"
        assert isinstance(get_registration_provider(), MockRegistrationProvider)

        injected = MockRegistrationProvider()
        app.config["REGISTRATION_PROVIDER_INSTANCE"] = injected
        assert get_registration_provider() is injected

        app.config.pop("REGISTRATION_PROVIDER_INSTANCE")
        app.config["REGISTRATION_PROVIDER_MODE"] = "unsupported"
        with pytest.raises(RegistrationProviderError, match="Unsupported"):
            get_registration_provider()
