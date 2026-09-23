import os
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from conftest import migrate
from sqlalchemy.exc import IntegrityError

from app.database import Base
from app.models import Document  # noqa: F401


def seed(connection):
    now = datetime.now(UTC)
    connection.execute(sa.text("INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'legacy', 'hash', :now)"), {"now": now})
    connection.execute(sa.text("INSERT INTO documents (id, user_id, title, filename, page_count, created_at) VALUES (1, 1, 'Study', 'study.pdf', 1, :now)"), {"now": now})
    connection.execute(sa.text("INSERT INTO document_pages (id, document_id, page_number, text) VALUES (1, 1, 1, 'Preserved text')"))
    connection.execute(sa.text("INSERT INTO conversations (id, user_id, document_id, title, created_at, updated_at) VALUES (1, 1, 1, 'Chat', :now, :now)"), {"now": now})
    connection.execute(sa.text("INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (1, 1, 'user', 'Preserved message', :now)"), {"now": now})


def verify(connection):
    assert MigrationContext.configure(connection).get_current_revision() == "0003_language_quiz_recovery"
    index = next(i for i in sa.inspect(connection).get_indexes("documents") if i["name"] == "ix_documents_user_file_hash")
    assert index["unique"]
    assert index["column_names"] == ["user_id", "file_hash"]


@pytest.mark.parametrize("initial", ["fresh", "legacy_unstamped", "legacy_stamped", "hashed"])
def test_sqlite_migration_preserves_existing_data(tmp_path, initial):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        if initial == "hashed":
            Base.metadata.create_all(connection)
            seed(connection)
            connection.execute(sa.text("UPDATE documents SET file_hash = :hash"), {"hash": "a" * 64})
        elif initial.startswith("legacy"):
            migrate(connection, "0001_baseline")
            seed(connection)
            if initial == "legacy_unstamped":
                connection.execute(sa.text("DROP TABLE alembic_version"))
        migrate(connection)
        migrate(connection)  # Repeat safely, including already-hashed adoption.
        verify(connection)
        if initial != "fresh":
            assert connection.scalar(sa.text("SELECT text FROM document_pages")) == "Preserved text"
            assert connection.scalar(sa.text("SELECT content FROM messages")) == "Preserved message"
            expected = "a" * 64 if initial == "hashed" else None
            assert connection.scalar(sa.text("SELECT file_hash FROM documents")) == expected
    engine.dispose()


def test_unique_hash_allows_nulls_and_other_users(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'unique.db'}")
    with engine.begin() as connection:
        migrate(connection)
        seed(connection)
        connection.execute(sa.text("INSERT INTO users (id, username, password_hash, created_at) SELECT 2, 'other', password_hash, created_at FROM users WHERE id=1"))
        for identifier, user_id, digest in [(2, 1, None), (3, 1, "a" * 64), (4, 2, "a" * 64)]:
            connection.execute(sa.text("INSERT INTO documents (id, user_id, title, filename, page_count, created_at, file_hash) SELECT :id, :user, title, filename, page_count, created_at, :hash FROM documents WHERE id=1"),
                               {"id": identifier, "user": user_id, "hash": digest})
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(sa.text("UPDATE documents SET file_hash = :hash WHERE id=1"), {"hash": "a" * 64})
    engine.dispose()


def test_partial_schema_refused_without_dropping_data(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'partial.db'}")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)"))
        connection.execute(sa.text("INSERT INTO users VALUES (1, 'keep')"))
        with pytest.raises(RuntimeError, match="Incomplete"):
            migrate(connection)
        assert connection.scalar(sa.text("SELECT username FROM users")) == "keep"
    engine.dispose()


@pytest.mark.parametrize("conflict", ["duplicates", "wrong_index"])
def test_hash_adoption_refuses_conflicts_without_modifying_rows(tmp_path, conflict):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'conflict.db'}")
    with engine.begin() as connection:
        migrate(connection, "0001_baseline")
        seed(connection)
        connection.execute(sa.text("ALTER TABLE documents ADD COLUMN file_hash VARCHAR(64)"))
        connection.execute(sa.text("UPDATE documents SET file_hash = :hash"), {"hash": "a" * 64})
        if conflict == "duplicates":
            connection.execute(sa.text("INSERT INTO documents SELECT 2, user_id, title, filename, page_count, created_at, file_hash FROM documents WHERE id=1"))
        else:
            connection.execute(sa.text("CREATE INDEX ix_documents_user_file_hash ON documents (file_hash)"))
        before = connection.execute(sa.text("SELECT id, file_hash FROM documents ORDER BY id")).all()
        with pytest.raises(RuntimeError):
            migrate(connection)
        assert connection.execute(sa.text("SELECT id, file_hash FROM documents ORDER BY id")).all() == before
    engine.dispose()


def test_startup_requires_explicit_migration(tmp_path, monkeypatch):
    from app import database

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'startup.db'}")
    monkeypatch.setattr(database, "engine", engine)
    with pytest.raises(RuntimeError, match="migration required"):
        database.verify_schema()
    assert sa.inspect(engine).get_table_names() == []
    with engine.begin() as connection:
        migrate(connection)
    database.verify_schema()
    engine.dispose()


@pytest.mark.parametrize("initial", ["fresh", "legacy_unstamped", "legacy_stamped", "hashed"])
def test_postgresql_migration_smoke(initial):
    url = os.environ.get("EDUTOOL_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("EDUTOOL_TEST_POSTGRES_URL not set; PostgreSQL smoke requires an isolated test service")
    engine = sa.create_engine(url)
    schema = "edutool_test_" + uuid.uuid4().hex
    try:
        with engine.begin() as connection:
            connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(sa.text(f'SET search_path TO "{schema}"'))
            if initial == "hashed":
                Base.metadata.create_all(connection)
                seed(connection)
            elif initial.startswith("legacy"):
                migrate(connection, "0001_baseline")
                seed(connection)
                if initial == "legacy_unstamped":
                    connection.execute(sa.text("DROP TABLE alembic_version"))
            migrate(connection)
            verify(connection)
            if initial != "fresh":
                assert connection.scalar(sa.text("SELECT content FROM messages")) == "Preserved message"
    finally:
        with engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()