import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.services import llm


def test_key_fallback_and_provider_error_privacy(monkeypatch):
    monkeypatch.setattr(llm, "RETRY_DELAY_SECONDS", 0)
    settings = Settings(_env_file=None, openrouter_api_keys="first,first,second")
    post = AsyncMock(side_effect=[httpx.Response(429, json={"error": {"message": "secret-provider-body"}}),
                                  httpx.Response(200, json={"choices": [{"message": {"content": "Success"}}]})])
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    assert asyncio.run(llm.complete(settings, [])) == "Success"
    assert post.await_count == 2
    post.reset_mock()
    post.side_effect = [httpx.Response(429, json={"error": {"message": "secret-provider-body"}})] * 4
    with pytest.raises(HTTPException) as error:
        asyncio.run(llm.complete(settings, []))
    assert error.value.status_code == 503
    assert "secret-provider-body" not in error.value.detail
    assert post.await_count == 4


def test_every_key_is_tried_for_any_failure_then_rate_limits_retry(monkeypatch):
    monkeypatch.setattr(llm, "RETRY_DELAY_SECONDS", 0)
    settings = Settings(_env_file=None, openrouter_api_keys="a,b,c")
    ok = httpx.Response(200, json={"choices": [{"message": {"content": "Success"}}]})
    post = AsyncMock(side_effect=[httpx.Response(400), httpx.Response(200, json={}), ok])
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    assert asyncio.run(llm.complete(settings, [])) == "Success"
    assert post.await_count == 3
    post.reset_mock()
    post.side_effect = [httpx.Response(429)] * 3 + [ok]
    assert asyncio.run(llm.complete(settings, [])) == "Success"
    assert post.await_count == 4
    post.reset_mock()
    post.side_effect = [httpx.Response(400)] * 3
    with pytest.raises(HTTPException) as error:
        asyncio.run(llm.complete(settings, []))
    assert error.value.status_code == 502
    assert post.await_count == 3


@pytest.mark.parametrize("payload", [{}, {"choices": [{"message": {"content": None}}]}, {"choices": []}])
def test_bad_provider_envelope_is_controlled(monkeypatch, payload):
    monkeypatch.setattr(httpx.AsyncClient, "post", AsyncMock(return_value=httpx.Response(200, json=payload)))
    with pytest.raises(HTTPException) as error:
        asyncio.run(llm.complete(Settings(_env_file=None, openrouter_api_keys="test"), []))
    assert error.value.status_code == 502