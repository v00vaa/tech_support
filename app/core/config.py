"""Configuration loaded only from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the support application."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="SUPPORT_", extra="ignore")

    environment: Literal["development", "testing", "production"] = "development"
    debug: bool = False
    secret_key: str = "development-only-change-me"
    database_url: str = "postgresql+psycopg://support:support@localhost:5432/support"
    database_echo: bool = False
    admin_email: str = "admin@example.com"

    # Shared rate-limit storage is required for multi-worker production deployments.
    rate_limit_storage_uri: str = "memory://"

    # Password recovery: links are signed, password-bound, and short-lived.
    public_base_url: str = "http://localhost:5000"
    password_reset_token_max_age_seconds: int = 1800
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_sender: str | None = None
    smtp_use_tls: bool = True
    smtp_timeout_seconds: float = 10.0
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"

    # Main-system registration integration. The mock provider is intended only for
    # local development; production must use the authenticated HTTP provider.
    registration_provider: Literal["mock", "http"] = "mock"
    registration_api_base_url: str | None = None
    registration_profile_path: str = "/api/v1/support/registration-profile"
    registration_redeem_path: str = "/api/v1/support/registration-token/redeem"
    registration_service_token: str | None = None
    registration_timeout_seconds: float = 5.0

    @model_validator(mode="after")
    def validate_runtime_security(self) -> "Settings":
        """Reject unsafe production settings and invalid timeout values."""
        if self.environment == "production" and self.debug:
            raise ValueError("SUPPORT_DEBUG cannot be enabled in production")
        if self.registration_provider == "http":
            if not self.registration_api_base_url or not self.registration_service_token:
                raise ValueError("HTTP registration integration requires API URL and service token")
            if not self.registration_api_base_url.startswith("https://"):
                raise ValueError("Registration API must use HTTPS")
        if self.environment == "production" and self.registration_provider != "http":
            raise ValueError("Production requires SUPPORT_REGISTRATION_PROVIDER=http")
        if self.environment == "production":
            if self.secret_key == "development-only-change-me":  # nosec B105 - sentinel, not a credential
                raise ValueError("Production requires a unique SUPPORT_SECRET_KEY")
            if not self.smtp_use_tls:
                raise ValueError("Production SMTP connections must use TLS")
            if bool(self.smtp_username) != bool(self.smtp_password):
                raise ValueError("SMTP username and password must be configured together")
            if not self.rate_limit_storage_uri.startswith(("redis://", "rediss://")):
                raise ValueError("Production requires shared Redis rate-limit storage")
            if not self.public_base_url.startswith("https://"):
                raise ValueError("Production public base URL must use HTTPS")
            if not self.smtp_host or not self.smtp_sender:
                raise ValueError("Production password recovery requires SMTP host and sender")
        if self.registration_timeout_seconds <= 0 or self.smtp_timeout_seconds <= 0:
            raise ValueError("Network timeouts must be positive")
        if self.password_reset_token_max_age_seconds <= 0:
            raise ValueError("Password reset token lifetime must be positive")
        if not 1 <= self.smtp_port <= 65535:
            raise ValueError("SMTP port is invalid")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
