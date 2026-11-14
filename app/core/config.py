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

    # Main-system registration integration. The mock provider is intended only for
    # local development; production must use the authenticated HTTP provider.
    registration_provider: Literal["mock", "http"] = "mock"
    registration_api_base_url: str | None = None
    registration_profile_path: str = "/api/v1/support/registration-profile"
    registration_redeem_path: str = "/api/v1/support/registration-token/redeem"
    registration_service_token: str | None = None
    registration_timeout_seconds: float = 5.0

    @model_validator(mode="after")
    def prohibit_debug_in_production(self) -> "Settings":
        """Avoid enabling Flask debug mode in a production process."""
        if self.environment == "production" and self.debug:
            raise ValueError("SUPPORT_DEBUG cannot be enabled in production")
        if self.registration_provider == "http":
            if not self.registration_api_base_url or not self.registration_service_token:
                raise ValueError(
                    "HTTP registration integration requires API URL and service token"
                )
            if not self.registration_api_base_url.startswith("https://"):
                raise ValueError("Registration API must use HTTPS")
        if self.environment == "production" and self.registration_provider != "http":
            raise ValueError("Production requires SUPPORT_REGISTRATION_PROVIDER=http")
        if self.registration_timeout_seconds <= 0:
            raise ValueError("SUPPORT_REGISTRATION_TIMEOUT_SECONDS must be positive")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
