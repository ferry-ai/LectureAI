"""Environment and provider catalog.

Keys stay on the server. The frontend only learns whether a provider is configured.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

load_dotenv(REPO_ROOT / ".env")
load_dotenv(BACKEND_ROOT / ".env")

ALLOWED_PROVIDERS = {"xai", "grok-account", "openai", "anthropic", "claude-account", "openrouter", "local", "demo"}

DEFAULT_MODELS = {
    "xai": "grok-4.7",
    "grok-account": "grok-4.7",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-5",
    "claude-account": "sonnet",
    "openrouter": "x-ai/grok-4",
    "local": "llama3.1",
    "demo": "heuristic",
}


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


XAI_API_KEY = _env("XAI_API_KEY")
OPENAI_API_KEY = _env("OPENAI_API_KEY")
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
OPENROUTER_API_KEY = _env("OPENROUTER_API_KEY")
LOCAL_LLM_BASE_URL = _env("LOCAL_LLM_BASE_URL")
LOCAL_LLM_API_KEY = _env("LOCAL_LLM_API_KEY")
DEEPGRAM_API_KEY = _env("DEEPGRAM_API_KEY")

DEFAULT_PROVIDER = _env("DEFAULT_LLM_PROVIDER", "xai") or "xai"
if DEFAULT_PROVIDER not in ALLOWED_PROVIDERS:
    DEFAULT_PROVIDER = "xai"

DEFAULT_MODEL = _env("DEFAULT_LLM_MODEL", DEFAULT_MODELS[DEFAULT_PROVIDER]) or DEFAULT_MODELS[DEFAULT_PROVIDER]

# The first pass waits for a real opening, not a one-sentence hook.
# Later passes wait at least this many seconds, matching the 20–40s lecture cadence.
ANALYSIS_MIN_INTERVAL = _float_env("ANALYSIS_MIN_INTERVAL", 20)
ANALYSIS_MIN_CHARS = _int_env("ANALYSIS_MIN_CHARS", 80)
ANALYSIS_FIRST_CHARS = _int_env("ANALYSIS_FIRST_CHARS", 480)


def clean_provider(value: str | None) -> str:
    name = (value or DEFAULT_PROVIDER).strip().lower()
    if name not in ALLOWED_PROVIDERS:
        raise ValueError(
            "Provider non supportato. Usa xai, grok-account, openai, anthropic, claude-account, openrouter, local o demo."
        )
    return name


def clean_model(value: str | None, provider: str) -> str:
    fallback = DEFAULT_MODELS.get(provider, "grok-4.7")
    name = (value or "").strip() or fallback
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,80}", name):
        raise ValueError("Nome modello non valido.")
    return name


def clean_language(value: str | None) -> str:
    name = (value or "it").strip().lower()
    if not re.fullmatch(r"[a-z]{2}(-[a-z]{2})?", name):
        return "it"
    return name


def _grok_account_entry() -> dict:
    # Imported here: config is loaded while the provider package is still starting.
    from app.services.providers.grok_account import grok_account_state

    state = grok_account_state()
    hints = {
        "ready": "",
        "missing": "Grok non è installato su questo PC.",
        "logged-out": "Lancia grok login in un terminale, poi ricarica la pagina.",
    }
    return {
        "id": "grok-account",
        "label": "Grok (account sul PC)",
        "models": ["grok-4.7", "grok-4.6", "grok-4.5"],
        "configured": state == "ready",
        "hint": hints.get(state, hints["logged-out"]),
        "via": "cli",
    }


def _claude_account_entry() -> dict:
    # Imported here: config is loaded while the provider package is still starting.
    from app.services.providers.claude_account import claude_account_state

    state = claude_account_state()
    hints = {
        "ready": "",
        "missing": "Claude Code non è installato su questo PC.",
        "api-key": "Claude Code sta usando una chiave API. Per il piano, lancia claude auth login e ricarica.",
        "logged-out": "Lancia claude auth login in un terminale, poi ricarica la pagina.",
    }
    return {
        "id": "claude-account",
        "label": "Claude (account sul PC)",
        "models": ["sonnet", "haiku", "opus"],
        "configured": state == "ready",
        "hint": hints.get(state, hints["logged-out"]),
        "via": "cli",
    }


def provider_is_ready(name: str) -> bool:
    if name == "demo":
        return True
    if name == "xai":
        return bool(XAI_API_KEY)
    if name == "openai":
        return bool(OPENAI_API_KEY)
    if name == "anthropic":
        return bool(ANTHROPIC_API_KEY)
    if name == "openrouter":
        return bool(OPENROUTER_API_KEY)
    if name == "local":
        return bool(LOCAL_LLM_BASE_URL)
    if name == "grok-account":
        from app.services.providers.grok_account import grok_account_state

        return grok_account_state() == "ready"
    if name == "claude-account":
        from app.services.providers.claude_account import claude_account_state

        return claude_account_state() == "ready"
    return False


def prefer_ready_provider(requested: str, ready: dict[str, bool]) -> str:
    """Use the requested provider when it can answer. Otherwise a logged-in CLI account."""

    if ready.get(requested):
        return requested
    for name in ("grok-account", "claude-account"):
        if ready.get(name):
            return name
    return requested


def _local_stt_ready() -> bool:
    import importlib.util

    return importlib.util.find_spec("faster_whisper") is not None


def provider_catalog() -> dict:
    ready = {name: provider_is_ready(name) for name in ALLOWED_PROVIDERS}
    chosen = prefer_ready_provider(DEFAULT_PROVIDER, ready)
    return {
        "default_provider": chosen,
        "default_model": DEFAULT_MODELS[chosen],
        "analysis": {
            "min_interval_s": ANALYSIS_MIN_INTERVAL,
            "min_chars": ANALYSIS_MIN_CHARS,
            "first_chars": ANALYSIS_FIRST_CHARS,
        },
        "providers": [
            {
                "id": "xai",
                "label": "xAI (Grok)",
                "models": ["grok-4.7", "grok-4.5", "grok-4.3"],
                "configured": bool(XAI_API_KEY),
                "hint": "XAI_API_KEY",
            },
            _grok_account_entry(),
            {
                "id": "openai",
                "label": "OpenAI",
                "models": ["gpt-4o-mini", "gpt-4.1-mini"],
                "configured": bool(OPENAI_API_KEY),
                "hint": "OPENAI_API_KEY",
            },
            {
                "id": "anthropic",
                "label": "Anthropic",
                "models": ["claude-sonnet-4-5", "claude-3-5-haiku-latest"],
                "configured": bool(ANTHROPIC_API_KEY),
                "hint": "ANTHROPIC_API_KEY",
            },
            _claude_account_entry(),
            {
                "id": "openrouter",
                "label": "OpenRouter",
                "models": ["x-ai/grok-4", "openai/gpt-4o-mini", "anthropic/claude-sonnet-4.5"],
                "configured": bool(OPENROUTER_API_KEY),
                "hint": "OPENROUTER_API_KEY",
            },
            {
                "id": "local",
                "label": "Locale (OpenAI-compatible)",
                "models": ["llama3.1", "qwen2.5"],
                "configured": bool(LOCAL_LLM_BASE_URL),
                "hint": "LOCAL_LLM_BASE_URL",
            },
            {
                "id": "demo",
                "label": "Demo locale",
                "models": ["heuristic"],
                "configured": True,
                "hint": "",
            },
        ],
        "stt": {
            "deepgram": bool(DEEPGRAM_API_KEY),
            "browser": True,
            "local": _local_stt_ready(),
        },
    }
