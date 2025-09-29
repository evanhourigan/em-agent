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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
