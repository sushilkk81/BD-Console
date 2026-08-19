from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://bdconsole:bdconsole@localhost:5432/bdconsole"
    jwt_secret: str = "dev-only-secret-change-me"
    cors_origins: list[str] = ["http://localhost:3000"]
    anthropic_api_key: str = ""
    tavily_api_key: str = ""

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        """Managed Postgres hosts (Render, Heroku-style) commonly hand out a bare
        postgres:// or postgresql:// connection string. SQLAlchemy 2.x no longer
        accepts the old postgres:// scheme at all, and a driverless postgresql://
        silently depends on whichever driver happens to be importable — pin it to
        the psycopg2 driver this app actually ships (see requirements.txt) so a
        hosted DATABASE_URL behaves the same as the local docker-compose one."""
        if v.startswith("postgres://"):
            return "postgresql+psycopg2://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            return "postgresql+psycopg2://" + v[len("postgresql://"):]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
