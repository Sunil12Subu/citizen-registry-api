"""Application settings.

Values are loaded from environment variables, or from a local .env file.
Every other module should call get_settings() instead of reading os.environ directly.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration the app needs. Field names match .env keys (case-insensitive)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env also holds POSTGRES_* values meant for Docker, not for us
    )

    app_env: str = "development"

    # SecretStr hides the value when printed or logged: it shows '**********'
    database_url: SecretStr
    api_key: SecretStr
    id_hash_secret: SecretStr


@lru_cache
def get_settings() -> Settings:
    """Build Settings once, then reuse the same object (cached)."""
    return Settings()
