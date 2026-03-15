"""
Application settings loaded from environment variables.
"""

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API Keys
    anthropic_api_key: str = "placeholder-key"
    tavily_api_key: str = "placeholder-key"
    ebird_token: str = "placeholder-token"

    # Frontend configuration
    frontend_base_url: str = "http://localhost:5173"

    # App settings
    app_name: str = "Birdle AI"
    debug: bool = False

    @model_validator(mode="after")
    def reject_placeholder_keys(self) -> "Settings":
        """Reject placeholder API keys at startup."""
        for field_name in ("anthropic_api_key", "tavily_api_key", "ebird_token"):
            value = getattr(self, field_name)
            if "placeholder" in value.lower():
                raise ValueError(
                    f"{field_name} is still set to a placeholder value. "
                    f"Please provide a real key in .env.local."
                )
        return self


# Singleton instance — will raise ValueError if placeholder keys are present
settings = Settings()
