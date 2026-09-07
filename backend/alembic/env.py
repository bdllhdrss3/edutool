"""Online, inspect-and-adopt migrations. Never log the configured database URL."""
from alembic import context
from sqlalchemy import create_engine, pool

from app import models  # noqa: F401 -- populate metadata for autogeneration
from app.core.config import get_settings
from app.database import Base

config = context.config


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Schema adoption requires an online connection; offline SQL is not supported")
elif config.attributes.get("connection") is not None:
    run(config.attributes["connection"])
else:
    engine = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            run(connection)
    finally:
        engine.dispose()