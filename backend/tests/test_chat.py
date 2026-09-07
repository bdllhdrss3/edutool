from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app import main
from app.models import Conversation, Message


def provider(monkeypatch, result):
    mock = AsyncMock(return_value=result)
    # Exercise the real structured/Pydantic validation, mock only provider I/O.
    monkeypatch.setattr("app.services.llm.complete", mock)
    return mock


def test_followup_receives_ordered_history_and_grounding(api, monkeypatch):
    doc = api.document()
    chat = api.conversation(doc, turns=3)
    mock = provider(monkeypatch, '{"classification":"answerable","answer":"Particles move down the gradient."}')
    response = api.client.post("/api/v1/chat", json={"document_id": doc.id, "conversation_id": chat.id, "content": "Why is that?"})
    assert response.status_code == 200
    messages = mock.call_args.args[1]
    assert [item["content"] for item in messages[1:-1]] == [f"{role} {i}" for i in range(3) for role in ("Question", "Answer")]
    assert messages[-1]["content"] == "Why is that?"
    assert "follow-ups" in messages[0]["content"]
    assert "Diffusion" in messages[0]["content"]
    assert api.db.scalar(select(func.count()).select_from(Message)) == 8


def test_history_budget_keeps_recent_complete_pairs(api):
    chat = api.conversation(api.document(), turns=4)
    api.settings.chat_history_messages = 5
    api.settings.chat_history_chars = len("Question 3Answer 3")
    assert main.conversation_history(api.db, chat.id) == [
        {"role": "user", "content": "Question 3"}, {"role": "assistant", "content": "Answer 3"}]


def test_history_drops_untrusted_roles_and_orphan_turns(api):
    chat = api.conversation(api.document(), turns=0)
    for role in ["assistant", "system", "user"]:
        api.db.add(Message(conversation_id=chat.id, role=role, content="Injected or orphan"))
    api.db.commit()
    assert main.conversation_history(api.db, chat.id) == []


@pytest.mark.parametrize("operation", ["chat", "summary", "translation"])
def test_document_mismatch_rejected_before_provider(api, monkeypatch, operation):
    doc, other = api.document(), api.document(content=b"other")
    chat = api.conversation(other)
    mock = provider(monkeypatch, "must not be called")
    result = api.client.post("/api/v1/chat", json={"document_id": doc.id, "conversation_id": chat.id,
                                               "content": "Explain", "operation": operation})
    assert result.status_code == 409
    mock.assert_not_awaited()


def test_cross_user_history_is_hidden(api, monkeypatch):
    doc = api.document()
    other_chat = api.conversation(api.document(owner=1), owner=1)
    mock = provider(monkeypatch, "must not be called")
    result = api.client.post("/api/v1/chat", json={"document_id": doc.id, "conversation_id": other_chat.id, "content": "Explain"})
    assert result.status_code == 404
    mock.assert_not_awaited()


@pytest.mark.parametrize("classification,expected", [("unrelated", "That is unrelated"), ("gibberish", "That looks like gibberish")])
def test_strict_rejections_are_deterministic(api, monkeypatch, classification, expected):
    import json
    doc = api.document()
    provider(monkeypatch, json.dumps({"classification": classification, "answer": "", "suggestions": ["What drives diffusion?"]}))
    result = api.client.post("/api/v1/chat", json={"document_id": doc.id, "content": "unrelated or nonsense"})
    assert result.status_code == 200
    assert result.json()["reply"].startswith(expected)
    assert "What drives diffusion?" in result.json()["reply"]


@pytest.mark.parametrize("payload", ["not JSON", '{"classification":"other"}',
    '{"classification":"answerable","answer":"   "}',
    '{"classification":"unrelated","answer":"fabricated answer"}',
    '{"classification":"gibberish","suggestions":[""]}'])
def test_invalid_classification_fails_closed_without_persistence(api, monkeypatch, payload):
    doc = api.document()
    provider(monkeypatch, payload)
    result = api.client.post("/api/v1/chat", json={"document_id": doc.id, "content": "Why?"})
    assert result.status_code == 502
    assert api.db.scalar(select(func.count()).select_from(Conversation)) == 0
    assert api.db.scalar(select(func.count()).select_from(Message)) == 0


@pytest.mark.parametrize("operation", ["summary", "translation"])
def test_utility_excludes_history_and_never_persists(api, monkeypatch, operation):
    doc = api.document()
    chat = api.conversation(doc)
    mock = AsyncMock(return_value="Tool result")
    monkeypatch.setattr(main, "complete", mock)
    result = api.client.post("/api/v1/chat", json={"document_id": doc.id, "page_number": 2,
        "conversation_id": chat.id, "operation": operation, "content": "In English"})
    assert result.status_code == 200
    assert result.json()["conversation_id"] is None
    messages = mock.call_args.args[1]
    assert len(messages) == 2
    assert "Active transport" in messages[0]["content"]
    assert "[Page 1]" not in messages[0]["content"]
    assert api.db.scalar(select(func.count()).select_from(Message)) == 2


def test_blank_source_or_missing_document_rejected(api):
    doc = api.document(texts=["", "Readable source " * 20])
    assert api.client.post("/api/v1/chat", json={"content": "Explain"}).status_code == 422
    assert api.client.post("/api/v1/chat", json={"document_id": doc.id, "page_number": 1, "content": "Explain"}).status_code == 422
    assert api.client.post("/api/v1/chat", json={"document_id": doc.id, "content": "   "}).status_code == 422