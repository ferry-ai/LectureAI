"""LLM provider registry.

Adapters only talk to a model and return a JSON object. The orchestrator decides
what happens next. Same split as the archived VCC orchestrator (`adapters/` vs `engine`).
"""

from __future__ import annotations

from app.services.providers.anthropic import AnthropicProvider
from app.services.providers.base import LLMProvider
from app.services.providers.claude_account import ClaudeAccountProvider
from app.services.providers.demo import DemoProvider
from app.services.providers.grok_account import GrokAccountProvider
from app.services.providers.local import LocalProvider
from app.services.providers.openai import OpenAIProvider
from app.services.providers.openrouter import OpenRouterProvider
from app.services.providers.xai import XAIProvider

_FACTORIES: dict[str, type[LLMProvider]] = {
    "xai": XAIProvider,
    "grok-account": GrokAccountProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "claude-account": ClaudeAccountProvider,
    "openrouter": OpenRouterProvider,
    "local": LocalProvider,
    "demo": DemoProvider,
}


def get_provider(name: str) -> LLMProvider:
    try:
        return _FACTORIES[name]()
    except KeyError as exc:
        raise ValueError(f"Provider sconosciuto: {name}") from exc
