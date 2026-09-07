import copy
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models import Conversation, Message


def valid_quiz():
    stems = [
        "Why does a steeper concentration gradient increase net diffusion?",
        "How does diffusion differ from active transport in its energy requirement?",
        "Why do particles continue moving when equilibrium is reached?",
        "How does the direction of net diffusion relate to concentration?",
        "A cell must move molecules against a gradient. Which process is needed?",
        "Two compartments reach equal concentration. What happens to particle movement?",
        "A concentration difference doubles. What change in diffusion is expected?",
        "A student says diffusion requires cellular energy. Which explanation corrects this?",
        "A student claims equilibrium stops particles. What is the misconception?",
        "A student says active transport always follows a gradient. Why is this incorrect?",
    ]
    return {"questions": [{"question": question, "options": ["Down the gradient", "Against the gradient with energy", "No molecular motion", "Equal net movement"],
        "correct_index": 0, "explanation": "A concentration difference creates net movement down the gradient.",
        "source_page": 1 if index % 2 == 0 else 2} for index, question in enumerate(stems)]}


def mock_provider(monkeypatch, payloads):
    mock = AsyncMock(side_effect=[json.dumps(payload) if not isinstance(payload, (str, Exception)) else payload for payload in payloads])
    monkeypatch.setattr("app.services.llm.complete", mock)
    return mock


def test_quiz_shape_prompt_selected_source_and_no_history(api, monkeypatch):
    doc = api.document()
    mock = mock_provider(monkeypatch, [valid_quiz()])
    result = api.client.post(f"/api/v1/documents/{doc.id}/quiz", json={"page_numbers": [2, 1, 2]})
    assert result.status_code == 200
    assert len(result.json()["questions"]) == 10
    prompt, source = mock.call_args.args[1]
    assert "misconceptions" in prompt["content"]
    assert "NEVER test who authored" in prompt["content"]
    assert "[Page 1]" in source["content"] and "[Page 2]" in source["content"]
    assert api.db.scalar(select(func.count()).select_from(Conversation)) == 0
    assert api.db.scalar(select(func.count()).select_from(Message)) == 0


@pytest.mark.parametrize("question", [
    "Who authored this document?", "Who wrote the textbook?", "What is the author's name?",
    "What is the title of this document?", "On which page is diffusion discussed?",
    "How many pages are in this document?", "What year was this document published?",
    "Which university prepared this document?", "Which section is active transport described in?",
])
def test_metadata_trivia_gets_one_repair(api, monkeypatch, question):
    doc = api.document()
    bad = valid_quiz()
    bad["questions"][0]["question"] = question
    mock = mock_provider(monkeypatch, [bad, valid_quiz()])
    result = api.client.post(f"/api/v1/documents/{doc.id}/quiz", json={"page_numbers": [1, 2]})
    assert result.status_code == 200
    assert mock.await_count == 2
    assert "Metadata trivia" in mock.call_args.args[1][-1]["content"]


@pytest.mark.parametrize("defect", ["json", "count", "source", "duplicate", "options", "empty", "index", "boolean"])
def test_invalid_quiz_repaired_exactly_once(api, monkeypatch, defect):
    doc = api.document()
    bad = copy.deepcopy(valid_quiz())
    if defect == "json":
        bad = "not json"
    elif defect == "count":
        bad["questions"].pop()
    elif defect == "source":
        bad["questions"][0]["source_page"] = 9
    elif defect == "duplicate":
        bad["questions"][1]["question"] = bad["questions"][0]["question"]
    elif defect == "options":
        bad["questions"][0]["options"] = ["A", " a ", "B", "C"]
    elif defect == "empty":
        bad["questions"][0]["options"][0] = " "
    elif defect == "index":
        bad["questions"][0]["correct_index"] = 4
    else:
        bad["questions"][0]["correct_index"] = True
    mock = mock_provider(monkeypatch, [bad, bad])
    result = api.client.post(f"/api/v1/documents/{doc.id}/quiz", json={"page_numbers": [1, 2]})
    assert result.status_code == 502
    assert "after one repair" in result.json()["detail"]
    assert mock.await_count == 2


def test_provider_outage_is_not_a_quiz_repair(api, monkeypatch):
    doc = api.document()
    mock = mock_provider(monkeypatch, [HTTPException(503, "Unavailable")])
    result = api.client.post(f"/api/v1/documents/{doc.id}/quiz", json={"page_numbers": [1]})
    assert result.status_code == 503
    assert mock.await_count == 1


@pytest.mark.parametrize("pages", [[], [0], [3]])
def test_invalid_selection_never_calls_provider(api, monkeypatch, pages):
    doc = api.document()
    mock = mock_provider(monkeypatch, [])
    assert api.client.post(f"/api/v1/documents/{doc.id}/quiz", json={"page_numbers": pages}).status_code == 422
    mock.assert_not_awaited()


def test_empty_page_selection_and_foreign_document(api, monkeypatch):
    doc = api.document(texts=[" ", "Substantive content " * 30])
    other = api.document(owner=1)
    mock = mock_provider(monkeypatch, [])
    assert api.client.post(f"/api/v1/documents/{doc.id}/quiz", json={"page_numbers": [1, 2]}).status_code == 422
    assert api.client.post(f"/api/v1/documents/{other.id}/quiz", json={"page_numbers": [1]}).status_code == 404
    mock.assert_not_awaited()


def test_selected_pages_all_survive_context_budget(api, monkeypatch):
    doc = api.document(texts=["FIRST " * 1000, "SECOND " * 1000, "UNSELECTED " * 1000])
    api.settings.quiz_context_limit = 1000
    mock = mock_provider(monkeypatch, [valid_quiz()])
    assert api.client.post(f"/api/v1/documents/{doc.id}/quiz", json={"page_numbers": [1, 2]}).status_code == 200
    source = mock.call_args.args[1][1]["content"]
    assert "FIRST" in source and "SECOND" in source and "UNSELECTED" not in source
    assert len(source) < 1050