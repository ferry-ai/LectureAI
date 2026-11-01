"""OpenRouter, OpenAI-compatible. Same shape as the RP hub's hosted routing."""

from __future__ import annotations

from app.config import OPENROUTER_API_KEY
from app.services.providers.base import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    def __init__(self) -> None:
        super().__init__(
            name="openrouter",
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            env_var="OPENROUTER_API_KEY",
            default_model="x-ai/grok-4",
        )
