import hashlib
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select

from app import main
from app.models import Conversation, Document, DocumentPage, Message


def count(api, model):
    return api.db.scalar(select(func.count()).select_from(model))


def test_routes_advertised(api):
    paths = api.client.get("/openapi.json").json()["paths"]
    for path in ["documents", "documents/{document_id}", "conversations", "conversations/{conversation_id}"]:
        assert "delete" in paths[f"/api/v1/{path}"]
    assert "post" in paths["/api/v1/documents/{document_id}/quiz"]


@pytest.mark.parametrize("resource", ["documents", "conversations"])
def test_individual_delete_is_owner_scoped(api, resource):
    document = api.document(owner=1)
    chat = api.conversation(document, owner=1)
    identifier = document.id if resource == "documents" else chat.id
    assert api.client.delete(f"/api/v1/{resource}/{identifier}").status_code == 404
    assert count(api, Document) == 1
    assert count(api, Conversation) == 1
    assert count(api, Message) == 2
    assert main.document_path(document.user_id, document.id).exists()


@pytest.mark.parametrize("missing_file", [False, True])
def test_delete_document_cleans_pages_chats_and_file(api, missing_file):
    doc = api.document()
    other = api.document(owner=1)
    api.conversation(doc)
    api.conversation(other, owner=1)
    path = main.document_path(doc.user_id, doc.id)
    if missing_file:
        path.unlink()
    assert api.client.delete(f"/api/v1/documents/{doc.id}").status_code == 204
    assert not path.exists()
    assert count(api, Document) == 1
    assert count(api, DocumentPage) == 2
    assert count(api, Conversation) == 1
    assert count(api, Message) == 2
    assert main.document_path(other.user_id, other.id).exists()
    assert api.client.delete(f"/api/v1/documents/{doc.id}").status_code == 404


def test_bulk_library_delete_preserves_other_user_and_unattached_chats(api):
    docs = [api.document(content=f"pdf{i}".encode()) for i in range(2)]
    for doc in docs:
        api.conversation(doc)
    api.conversation()  # Legacy unattached chat is not part of the library.
    other = api.document(owner=1)
    api.conversation(other, owner=1)
    assert api.client.delete("/api/v1/documents").status_code == 204
    assert count(api, Document) == 1
    assert count(api, DocumentPage) == 2
    assert count(api, Conversation) == 2
    assert count(api, Message) == 4
    assert all(not main.document_path(doc.user_id, doc.id).exists() for doc in docs)
    assert main.document_path(other.user_id, other.id).exists()
    assert api.client.delete("/api/v1/documents").status_code == 204


def test_individual_and_bulk_chat_delete(api):
    doc = api.document()
    one, two = api.conversation(doc), api.conversation(doc)
    api.conversation(api.document(owner=1), owner=1)
    assert api.client.delete(f"/api/v1/conversations/{one.id}").status_code == 204
    assert count(api, Message) == 4
    assert api.client.get(f"/api/v1/conversations/{two.id}").status_code == 200
    assert api.client.delete("/api/v1/conversations").status_code == 204
    assert count(api, Conversation) == 1
    assert count(api, Message) == 2
    assert count(api, Document) == 2
    assert main.document_path(doc.user_id, doc.id).exists()


def test_dedup_same_bytes_not_filename_and_per_user(api, monkeypatch):
    parser = Mock(return_value=["Extracted content"])
    monkeypatch.setattr(main, "extract_pdf_pages", parser)
    content = b"%PDF-identical bytes"
    first = api.client.post("/api/v1/documents", files={"file": ("first.pdf", content, "application/pdf")})
    assert first.status_code == 201
    assert first.json()["existing"] is False
    for filename in ["first.pdf", "renamed.pdf"]:
        duplicate = api.client.post("/api/v1/documents", files={"file": (filename, content, "application/pdf")})
        assert duplicate.status_code == 200
        assert duplicate.json()["existing"] is True
        assert duplicate.json()["id"] == first.json()["id"]
    assert parser.call_count == 1
    changed = api.client.post("/api/v1/documents", files={"file": ("first.pdf", content + b"different", "application/pdf")})
    assert changed.status_code == 201
    api.identity["id"] = api.users[1].id
    separate = api.client.post("/api/v1/documents", files={"file": ("first.pdf", content, "application/pdf")})
    assert separate.status_code == 201
    assert separate.json()["id"] != first.json()["id"]
    assert parser.call_count == 3
    assert count(api, Document) == 3


def test_legacy_backfill_canonical_duplicate_persisted(api, monkeypatch):
    content = b"%PDF-legacy"
    canonical = api.document(content=content)
    duplicate = api.document(content=content)
    missing = api.document(content=b"missing")
    main.document_path(missing.user_id, missing.id).unlink()
    other = api.document(owner=1, content=content)
    parser = Mock(side_effect=AssertionError("Duplicate must not be parsed"))
    monkeypatch.setattr(main, "extract_pdf_pages", parser)
    result = api.client.post("/api/v1/documents", files={"file": ("renamed.pdf", content, "application/pdf")})
    assert result.status_code == 200
    assert result.json()["id"] == canonical.id
    api.db.expire_all()
    assert canonical.file_hash == hashlib.sha256(content).hexdigest()
    assert duplicate.file_hash is None
    assert missing.file_hash is None
    assert other.file_hash is None
    api.db.rollback()  # A new transaction must still see the committed backfill.
    assert canonical.file_hash == hashlib.sha256(content).hexdigest()


def test_existing_hashed_row_wins_over_legacy(api, monkeypatch):
    content = b"%PDF-known"
    legacy = api.document(content=content)
    canonical = api.document(content=content, file_hash=hashlib.sha256(content).hexdigest())
    monkeypatch.setattr(main, "extract_pdf_pages", Mock(side_effect=AssertionError))
    result = api.client.post("/api/v1/documents", files={"file": ("new.pdf", content, "application/pdf")})
    assert result.json()["id"] == canonical.id
    assert legacy.file_hash is None


def test_upload_validation(api):
    assert api.client.post("/api/v1/documents", files={"file": ("bad.txt", b"x", "text/plain")}).status_code == 415
    assert api.client.post("/api/v1/documents", files={"file": ("bad.pdf", b"bad", "application/pdf")}).status_code == 422
    assert count(api, Document) == 0