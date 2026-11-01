"""Any local OpenAI-compatible server (Ollama, LM Studio, vLLM)."""

from __future__ import annotations

from app.config import LOCAL_LLM_API_KEY, LOCAL_LLM_BASE_URL
from app.services.providers.base import OpenAICompatibleProvider


class LocalProvider(OpenAICompatibleProvider):
    def __init__(self) -> None:
        super().__init__(
            name="local",
            api_key=LOCAL_LLM_API_KEY or ("local" if LOCAL_LLM_BASE_URL else ""),
            base_url=LOCAL_LLM_BASE_URL or "http://127.0.0.1:11434/v1",
            env_var="LOCAL_LLM_BASE_URL",
            default_model="llama3.1",
        )
