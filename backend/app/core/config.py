from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://edutool:change-me@postgres:5432/edutool"
    redis_url: str = "redis://redis:6379/0"
    session_secret: str = "development-only-change-me"
    openrouter_api_keys: str = ""
    openrouter_model: str = "google/gemini-2.5-flash"
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "edutool-minio"
    s3_secret_key: str = "change-me"
    s3_bucket: str = "edutool-documents"
    upload_dir: str = "uploads"
    cookie_secure: bool = False

    @property
    def openrouter_keys(self) -> list[str]:
        keys = (key.strip() for key in self.openrouter_api_keys.split(","))
        return list(dict.fromkeys(key for key in keys if key))


@lru_cache
def get_settings() -> Settings:
    return Settings()
