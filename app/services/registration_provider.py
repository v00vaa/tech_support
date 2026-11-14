"""Adapters for fetching and redeeming one-time registration links.

The HTTP contract is deliberately small so an installation can integrate with
any primary system without changing the registration workflow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from flask import current_app


class RegistrationProviderError(RuntimeError):
    """The configured primary-system integration is unavailable or malformed."""


class RegistrationTokenInvalid(RegistrationProviderError):
    """The handoff token is unknown, expired, revoked, or already consumed."""


@dataclass(frozen=True, slots=True)
class RegistrationProfile:
    external_id: str
    name: str | None = None
    email: str | None = None
    phone: str | None = None


class RegistrationProvider(Protocol):
    def get_profile(self, token: str) -> RegistrationProfile: ...

    def redeem_token(self, token: str, *, idempotency_key: str) -> None: ...


class MockRegistrationProvider:
    """Development-only provider simulating the primary-system API contract."""

    _profiles = {
        "DEMO-TOKEN-1001": RegistrationProfile(
            external_id="DEMO-1001",
            name="Демонстрационный клиент",
            email=None,
            phone=None,
        )
    }

    def get_profile(self, token: str) -> RegistrationProfile:
        profile = self._profiles.get(token)
        if profile is None:
            raise RegistrationTokenInvalid("Unknown or expired demo registration token")
        return profile

    def redeem_token(self, token: str, *, idempotency_key: str) -> None:
        # The mock intentionally accepts repeated redemption to model an idempotent API.
        self.get_profile(token)


class HttpRegistrationProvider:
    """Server-to-server adapter for the main system."""

    def __init__(
        self,
        *,
        base_url: str,
        service_token: str,
        profile_path: str,
        redeem_path: str,
        timeout: float,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.service_token = service_token
        self.profile_path = profile_path.lstrip("/")
        self.redeem_path = redeem_path.lstrip("/")
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        handoff_token: str,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.service_token}",
            "X-Registration-Token": handoff_token,
        }
        body = None
        if method == "POST":
            headers["Content-Type"] = "application/json"
            if idempotency_key:
                headers["Idempotency-Key"] = idempotency_key
            body = b"{}"
        request = Request(
            urljoin(self.base_url, path),
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw_body = response.read()
                payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except HTTPError as error:
            if error.code in {404, 410}:
                raise RegistrationTokenInvalid("Registration token is invalid or expired") from error
            raise RegistrationProviderError(
                f"Primary system returned HTTP {error.code}"
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise RegistrationProviderError("Primary system request failed") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RegistrationProviderError("Primary system returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise RegistrationProviderError("Primary system response must be a JSON object")
        return payload

    def get_profile(self, token: str) -> RegistrationProfile:
        payload = self._request("GET", self.profile_path, handoff_token=token)
        try:
            external_id = payload["external_id"]
            if not isinstance(external_id, str) or not external_id.strip():
                raise ValueError("external_id is required")
            return RegistrationProfile(
                external_id=external_id.strip(),
                name=_optional_string(payload.get("name")),
                email=_optional_string(payload.get("email")),
                phone=_optional_string(payload.get("phone")),
            )
        except (KeyError, ValueError, TypeError) as error:
            raise RegistrationProviderError("Primary system profile schema is invalid") from error

    def redeem_token(self, token: str, *, idempotency_key: str) -> None:
        self._request(
            "POST",
            self.redeem_path,
            handoff_token=token,
            idempotency_key=idempotency_key,
        )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("Profile fields must be strings or null")
    value = value.strip()
    return value or None


def get_registration_provider() -> RegistrationProvider:
    """Build the configured adapter; tests may inject an implementation in Flask config."""
    injected = current_app.config.get("REGISTRATION_PROVIDER_INSTANCE")
    if injected is not None:
        return injected
    mode = current_app.config["REGISTRATION_PROVIDER_MODE"]
    if mode == "mock":
        return MockRegistrationProvider()
    if mode == "http":
        return HttpRegistrationProvider(
            base_url=current_app.config["REGISTRATION_API_BASE_URL"],
            service_token=current_app.config["REGISTRATION_SERVICE_TOKEN"],
            profile_path=current_app.config["REGISTRATION_PROFILE_PATH"],
            redeem_path=current_app.config["REGISTRATION_REDEEM_PATH"],
            timeout=current_app.config["REGISTRATION_TIMEOUT_SECONDS"],
        )
    raise RegistrationProviderError("Unsupported registration provider mode")
