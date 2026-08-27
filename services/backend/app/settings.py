"""
Application settings loaded from environment variables.
"""

import os

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

    # LangSmith observability (optional — tracing is off unless enabled)
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "birdle"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

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

    @model_validator(mode="after")
    def export_langsmith_env(self) -> "Settings":
        """Propagate LangSmith config to os.environ so LangChain/LangGraph
        auto-instrument. LangChain reads these from the environment directly,
        not from Pydantic, so they must be exported before the graph is built.
        """
        if self.langsmith_tracing and self.langsmith_api_key:
            os.environ.setdefault("LANGSMITH_TRACING", "true")
            os.environ.setdefault("LANGSMITH_API_KEY", self.langsmith_api_key)
            os.environ.setdefault("LANGSMITH_PROJECT", self.langsmith_project)
            os.environ.setdefault("LANGSMITH_ENDPOINT", self.langsmith_endpoint)
        return self


# Singleton instance — will raise ValueError if placeholder keys are present
settings = Settings()
