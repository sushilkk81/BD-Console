from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://bdconsole:bdconsole@localhost:5432/bdconsole"
    jwt_secret: str = "dev-only-secret-change-me"
    cors_origins: list[str] = ["http://localhost:3000"]
    anthropic_api_key: str = ""
    tavily_api_key: str = ""

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
