"""xAI / Grok provider. OpenAI-compatible endpoint, key in XAI_API_KEY."""

from __future__ import annotations

from app.config import XAI_API_KEY
from app.services.providers.base import OpenAICompatibleProvider


class XAIProvider(OpenAICompatibleProvider):
    def __init__(self) -> None:
        super().__init__(
            name="xai",
            api_key=XAI_API_KEY,
            base_url="https://api.x.ai/v1",
            env_var="XAI_API_KEY",
            default_model="grok-4.7",
        )
