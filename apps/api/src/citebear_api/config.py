"""Application configuration.

Env-only, validated at startup: a missing required variable fails the boot
(via the lifespan hook in app.py), never an individual request.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    gateway_base_url: str = "https://ai-gateway.vercel.sh/v1"
    gateway_api_key: str
    internal_api_key: str
    admin_password: str
    blob_read_write_token: str
    chat_model: str = "anthropic/claude-haiku-4-5"
    rerank_model: str = "anthropic/claude-haiku-4-5"
    embedding_model: str = "openai/text-embedding-3-small"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue] — fields come from env
