import asyncio
import json
from typing import TypeVar

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ValidationError

from app.core.config import Settings

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)
TRANSIENT_STATUSES = {408, 429, 500, 502, 503, 504}
ACCOUNT_STATUSES = {401, 402, 403}
RETRY_DELAY_SECONDS = 2.0


class InvalidStructuredResponse(HTTPException):
    def __init__(self) -> None:
        super().__init__(502, "The AI provider returned an invalid structured response. Please try again.")


def _json_payload(content: str) -> object:
    value = content.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[-1]
        value = value.rsplit("```", 1)[0]
    return json.loads(value)


async def complete(settings: Settings, messages: list[dict[str, str]], max_tokens: int = 1000) -> str:
    if not settings.openrouter_keys:
        raise HTTPException(503, "AI is not configured yet. Add an OpenRouter key in backend/.env.")

    provider_errors: list[str] = []
    transient = False
    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
        # A second pass after a short pause covers rate limits that clear within seconds.
        for round_number in range(2):
            if round_number:
                if not transient:
                    break
                await asyncio.sleep(RETRY_DELAY_SECONDS)
            transient = False
            for api_key in settings.openrouter_keys:
                try:
                    candidate = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={"model": settings.openrouter_model, "messages": messages, "max_tokens": max_tokens},
                    )
                except httpx.RequestError as exc:
                    provider_errors.append(type(exc).__name__)
                    transient = True
                    continue
                if candidate.is_success:
                    try:
                        content = candidate.json()["choices"][0]["message"]["content"]
                        if isinstance(content, str) and content.strip():
                            return content
                    except (KeyError, IndexError, TypeError, ValueError):
                        pass
                    provider_errors.append("invalid response")
                    continue
                # Never echo provider bodies: they can contain credentials or request content.
                provider_errors.append(f"HTTP {candidate.status_code}")
                if candidate.status_code in TRANSIENT_STATUSES:
                    transient = True

    detail = provider_errors[-1] if provider_errors else "No provider response"
    if detail == "invalid response":
        raise HTTPException(502, "The AI provider returned an invalid response")
    if detail.startswith("HTTP") and int(detail[5:]) not in TRANSIENT_STATUSES | ACCOUNT_STATUSES:
        raise HTTPException(502, "The AI provider rejected the request")
    raise HTTPException(503, f"The AI provider is temporarily unavailable ({detail})")


async def structured(
    settings: Settings,
    messages: list[dict[str, str]],
    response_model: type[ResponseModel],
    max_tokens: int = 1200,
) -> ResponseModel:
    response = await complete(settings, messages, max_tokens)
    try:
        return response_model.model_validate(_json_payload(response))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise InvalidStructuredResponse() from exc