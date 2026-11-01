"""OpenAI provider."""

from __future__ import annotations

from app.config import OPENAI_API_KEY
from app.services.providers.base import OpenAICompatibleProvider


class OpenAIProvider(OpenAICompatibleProvider):
    def __init__(self) -> None:
        super().__init__(
            name="openai",
            api_key=OPENAI_API_KEY,
            base_url="https://api.openai.com/v1",
            env_var="OPENAI_API_KEY",
            default_model="gpt-4o-mini",
        )
