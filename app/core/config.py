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

    @model_validator(mode="after")
    def prohibit_debug_in_production(self) -> "Settings":
        """Avoid enabling Flask debug mode in a production process."""
        if self.environment == "production" and self.debug:
            raise ValueError("SUPPORT_DEBUG cannot be enabled in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
