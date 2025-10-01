from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, case_sensitive=False)

    env: str = "development"
    app_name: str = "EM Agent Gateway"
    app_version: str = "0.1.0"
    cors_allow_origins: list[str] = ["*"]

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"
    rag_url: str = "http://rag:8000"
    slack_signing_secret: str | None = None
    slack_signing_required: bool = False
    slack_webhook_url: str | None = None
    slack_bot_token: str | None = None
    slack_default_channel: str | None = None

    # Tracing
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
