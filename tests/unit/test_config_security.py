"""Security validation tests for environment settings."""

import pytest

from app.core.config import Settings


def test_http_registration_requires_credentials_and_https():
    with pytest.raises(ValueError, match="API URL and service token"):
        Settings(registration_provider="http")

    with pytest.raises(ValueError, match="must use HTTPS"):
        Settings(
            registration_provider="http",
            registration_api_base_url="http://main.example.test",
            registration_service_token="service-token",
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"registration_provider": "mock"}, "requires SUPPORT_REGISTRATION_PROVIDER=http"),
        ({"secret_key": "development-only-change-me"}, "unique SUPPORT_SECRET_KEY"),
        ({"smtp_use_tls": False}, "SMTP connections must use TLS"),
        ({"smtp_username": "user"}, "configured together"),
        ({"rate_limit_storage_uri": "memory://"}, "shared Redis"),
        ({"public_base_url": "http://support.example.test"}, "must use HTTPS"),
        ({"smtp_host": None}, "requires SMTP host and sender"),
    ],
)
def test_production_rejects_unsafe_configuration(overrides, message):
    production = {
        "environment": "production",
        "secret_key": "unique-production-secret",
        "registration_provider": "http",
        "registration_api_base_url": "https://main.example.test",
        "registration_service_token": "service-token",
        "rate_limit_storage_uri": "redis://localhost:6379/0",
        "public_base_url": "https://support.example.test",
        "smtp_host": "smtp.example.test",
        "smtp_sender": "support@example.test",
    }
    production.update(overrides)

    with pytest.raises(ValueError, match=message):
        Settings(**production)


def test_production_accepts_complete_secure_configuration():
    settings = Settings(
        environment="production",
        secret_key="unique-production-secret",
        registration_provider="http",
        registration_api_base_url="https://main.example.test",
        registration_service_token="service-token",
        rate_limit_storage_uri="rediss://localhost:6379/0",
        public_base_url="https://support.example.test",
        smtp_host="smtp.example.test",
        smtp_sender="support@example.test",
        smtp_username="smtp-user",
        smtp_password="smtp-password",
    )

    assert settings.environment == "production"


@pytest.mark.parametrize(
    "overrides",
    [
        {"registration_timeout_seconds": 0},
        {"smtp_timeout_seconds": 0},
        {"password_reset_token_max_age_seconds": 0},
        {"smtp_port": 0},
        {"smtp_port": 65536},
    ],
)
def test_settings_reject_invalid_network_and_token_limits(overrides):
    with pytest.raises(ValueError):
        Settings(**overrides)
