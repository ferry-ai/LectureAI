"""Provider interface and the OpenAI-compatible HTTP client used by xAI and OpenAI."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod

import httpx

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


class MissingCredentials(Exception):
    def __init__(self, env_var: str, provider: str) -> None:
        self.env_var = env_var
        self.provider = provider
        super().__init__(f"Manca {env_var} per {provider}.")


class ProviderError(Exception):
    """The upstream model failed or returned something we cannot parse."""


class TransportError(ProviderError):
    """The channel failed. Distinct from a reply that arrived but is the wrong shape.

    Same split used by the VCC orchestrator adapters: a timeout may be retried once;
    a reply that does not match the contract is not a transport failure.
    """

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def complete_json(self, system: str, user: str, model: str) -> dict:
        """Return a decoded JSON object. Callers validate it against LlmDelta."""


def parse_json_object(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = _FENCE.sub("", text).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = _OBJECT.search(text)
        if match is None:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ProviderError("Il modello ha restituito JSON che non è un oggetto.")
    return parsed


def message_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or part.get("content") or ""))
        return "".join(parts)
    return str(content or "")


class OpenAICompatibleProvider(LLMProvider):
    """Chat completions at `{base_url}/chat/completions`.

    xAI is called this way: OpenAI SDK shape, base URL https://api.x.ai/v1,
    model id from the current docs (grok-4.7). See https://docs.x.ai.
    """

    def __init__(self, name: str, api_key: str, base_url: str, env_var: str, default_model: str) -> None:
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.env_var = env_var
        self.default_model = default_model

    async def complete_json(self, system: str, user: str, model: str) -> dict:
        if not self.api_key:
            raise MissingCredentials(self.env_var, self.name)
        chosen = model or self.default_model
        payload = {
            "model": chosen,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=40) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise TransportError(f"Timeout verso {self.name}.") from exc
        except httpx.HTTPError as exc:
            raise TransportError(f"{self.name} non raggiungibile: {exc.__class__.__name__}") from exc

        if response.status_code in (401, 403):
            raise ProviderError(f"Accesso rifiutato da {self.name}. Controlla {self.env_var}.")
        if response.status_code in (408, 409, 429, 500, 502, 503, 504):
            raise TransportError(f"{self.name} ha risposto {response.status_code}.")
        if response.status_code >= 400:
            detail = response.text[:240].replace("\n", " ")
            raise ProviderError(f"{self.name} ha risposto {response.status_code}: {detail}")

        try:
            body = response.json()
            content = message_text(body["choices"][0]["message"]["content"])
            return parse_json_object(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Risposta non interpretabile da {self.name}.") from exc
