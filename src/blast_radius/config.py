"""Application configuration module using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for Cloud Blast-Radius Simulator."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Cloud Blast-Radius Simulator"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )

    # Ingestion limits
    max_plan_size_bytes: int = 10 * 1024 * 1024  # 10 MB limit
    analysis_timeout_seconds: int = 30

    # Logging settings
    log_level: str = "INFO"
    log_json: bool = True

    # Secret redaction keywords (case-insensitive substring matches on keys and values)
    redact_keys: list[str] = Field(
        default_factory=lambda: [
            "password",
            "secret",
            "token",
            "api_key",
            "apikey",
            "access_key",
            "private_key",
            "auth",
            "credential",
            "certificate",
            "master_user_password",
            "admin_password",
        ]
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
