from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://edutool:change-me@postgres:5432/edutool"
    redis_url: str = "redis://redis:6379/0"
    session_secret: str = "development-only-change-me"
    openrouter_api_keys: str = ""
    openrouter_model: str = "google/gemini-2.5-flash"
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "edutool-minio"
    s3_secret_key: str = "change-me"
    s3_bucket: str = "edutool-documents"

    @property
    def openrouter_keys(self) -> list[str]:
        return [key.strip() for key in self.openrouter_api_keys.split(",") if key.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
