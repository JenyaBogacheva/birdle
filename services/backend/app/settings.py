"""
Application settings loaded from environment variables.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API Keys (placeholders for MVP)
    openai_api_key: str = "placeholder-key"
    ebird_token: str = "placeholder-token"

    # Frontend configuration
    frontend_base_url: str = "http://localhost:5173"

    # App settings
    app_name: str = "Birdle AI"
    debug: bool = True


# Singleton instance
settings = Settings()
