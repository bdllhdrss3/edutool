import os
from pathlib import Path
from types import SimpleNamespace

# Set before application imports: tests must never connect to the user's configured database.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["OPENROUTER_API_KEYS"] = ""

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import main
from app.auth import current_user
from app.core.config import Settings
from app.database import get_db
from app.models import Conversation, Document, DocumentPage, Message, User

BACKEND = Path(__file__).resolve().parents[1]


def migrate(connection, revision="head"):
    config = Config(str(BACKEND / "alembic.ini"))
    config.attributes["connection"] = connection
    command.upgrade(config, revision)


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    with engine.begin() as connection:
        migrate(connection)
    settings = Settings(_env_file=None, database_url="sqlite://", upload_dir=str(tmp_path))
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "verify_schema", lambda: None)
    with Session(engine, expire_on_commit=False, autoflush=False) as db:
        users = [User(username=f"user{i}", password_hash="not-used") for i in range(2)]
        db.add_all(users)
        db.commit()
        identity = {"id": users[0].id}
        main.app.dependency_overrides[get_db] = lambda: db
        main.app.dependency_overrides[current_user] = lambda: db.get(User, identity["id"])

        def document(owner=0, texts=None, content=b"%PDF-fixture", file_hash=None):
            texts = texts if texts is not None else [
                ("Diffusion is the net movement of particles from high to low concentration. "
                "A larger concentration gradient increases the rate of diffusion. "
                "At equilibrium particles still move randomly but there is no net movement."),
                ("Active transport uses energy to move substances against a concentration gradient. "
                "Membrane carrier proteins transfer specific molecules and require cellular energy."),
            ]
            row = Document(user_id=users[owner].id, title="Biology", filename="biology.pdf",
                           page_count=len(texts), file_hash=file_hash)
            db.add(row)
            db.flush()
            db.add_all(DocumentPage(document_id=row.id, page_number=i, text=text)
                       for i, text in enumerate(texts, 1))
            main.document_path(row.user_id, row.id).write_bytes(content)
            db.commit()
            return row

        def conversation(document=None, owner=0, turns=1):
            row = Conversation(user_id=users[owner].id, document_id=document.id if document else None,
                               title="Explain diffusion")
            db.add(row)
            db.flush()
            for i in range(turns):
                db.add_all([Message(conversation_id=row.id, role="user", content=f"Question {i}"),
                            Message(conversation_id=row.id, role="assistant", content=f"Answer {i}")])
            db.commit()
            return row

        with TestClient(main.app) as client:
            yield SimpleNamespace(client=client, db=db, users=users, identity=identity,
                                  document=document, conversation=conversation, settings=settings)
        main.app.dependency_overrides.clear()
    engine.dispose()