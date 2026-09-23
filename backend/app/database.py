from collections.abc import Generator

from alembic.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def verify_schema() -> None:
    """Startup is read-only; operators migrate explicitly before starting a worker."""
    with engine.connect() as connection:
        revision = MigrationContext.configure(connection).get_current_revision()
    if revision != "0003_language_quiz_recovery":
        raise RuntimeError("Database migration required: run python -m alembic upgrade head in backend before starting the API")

def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session