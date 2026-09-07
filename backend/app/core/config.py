from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://edutool:change-me@postgres:5432/edutool"
    redis_url: str = "redis://redis:6379/0"
    session_secret: str = "development-only-change-me"
    openrouter_api_keys: str = ""
    openrouter_model: str = "google/gemini-2.5-flash"
    llm_timeout_seconds: float = 45
    chat_history_messages: int = Field(default=12, ge=2, le=100)
    chat_history_chars: int = Field(default=16000, ge=1000, le=100000)
    document_context_limit: int = Field(default=30000, ge=1000, le=100000)
    quiz_context_limit: int = Field(default=45000, ge=1000, le=100000)
    pdf_max_pages: int = Field(default=300, ge=1, le=2000)
    pdf_max_ocr_pages: int = Field(default=30, ge=0, le=300)
    pdf_ocr_max_pixels: int = Field(default=4000000, ge=10000, le=16000000)
    pdf_ocr_max_dimension: int = Field(default=2400, ge=100, le=4096)
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
