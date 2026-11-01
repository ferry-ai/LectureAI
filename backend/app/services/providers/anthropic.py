"""Anthropic Messages API. The model is asked for a single JSON object."""

from __future__ import annotations

import json

import httpx

from app.config import ANTHROPIC_API_KEY
from app.services.providers.base import (
    LLMProvider,
    MissingCredentials,
    ProviderError,
    TransportError,
    message_text,
    parse_json_object,
)


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    async def complete_json(self, system: str, user: str, model: str) -> dict:
        if not ANTHROPIC_API_KEY:
            raise MissingCredentials("ANTHROPIC_API_KEY", self.name)
        payload = {
            "model": model or "claude-sonnet-4-5",
            "max_tokens": 1500,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=40) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise TransportError("Timeout verso Anthropic.") from exc
        except httpx.HTTPError as exc:
            raise TransportError(f"Anthropic non raggiungibile: {exc.__class__.__name__}") from exc

        if response.status_code in (401, 403):
            raise ProviderError("Accesso rifiutato da Anthropic. Controlla ANTHROPIC_API_KEY.")
        if response.status_code in (408, 409, 429, 500, 502, 503, 504):
            raise TransportError(f"Anthropic ha risposto {response.status_code}.")
        if response.status_code >= 400:
            detail = response.text[:240].replace("\n", " ")
            raise ProviderError(f"Anthropic ha risposto {response.status_code}: {detail}")

        try:
            body = response.json()
            content = message_text(body.get("content"))
            return parse_json_object(content)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ProviderError("Risposta non interpretabile da Anthropic.") from exc
