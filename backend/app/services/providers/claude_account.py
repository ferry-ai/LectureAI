"""Lecture delta through the official Claude Code binary already logged in on this PC.

LectureAI does not see the password or the OAuth token. It starts `claude --print`
in an empty folder, with tools turned off, and reads the JSON the process prints.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from app.services.providers.base import (
    LLMProvider,
    MissingCredentials,
    ProviderError,
    TransportError,
    parse_json_object,
)

# A lecture pass is one shot. 75s covers a slow Pro reply; a timeout is not retried.
_TIMEOUT_S = 75
_PROBE_TIMEOUT_S = 8
_PROBE_TTL_S = 30

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "new_keywords": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "term": {"type": "string"},
                    "related_to": {"type": "array", "items": {"type": "string"}},
                    "importance": {"type": "integer"},
                },
                "required": ["term", "related_to", "importance"],
            },
        },
        "questions": {"type": "array", "items": {"type": "string"}},
        "expansions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"term": {"type": "string"}, "explanation": {"type": "string"}},
                "required": ["term", "explanation"],
            },
        },
        "slide_hints": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "concept": {"type": "string"},
                    "possible_slide_topic": {"type": "string"},
                },
                "required": ["concept", "possible_slide_topic"],
            },
        },
    },
    "required": ["new_keywords", "questions", "expansions", "slide_hints"],
}

Runner = Callable[[list[str], str, dict[str, str]], tuple[int, str, str]]

_probe_cache: tuple[float, str] | None = None


def claude_binary() -> str | None:
    override = os.getenv("LECTUREAI_CLAUDE_BIN", "").strip()
    if override:
        return override if Path(override).is_file() else None
    found = shutil.which("claude")
    if found:
        return found
    candidate = Path.home() / ".local" / "bin" / "claude.exe"
    return str(candidate) if candidate.is_file() else None


def claude_account_state() -> str:
    """ready, missing, logged-out, or api-key. Cached briefly so the catalog stays cheap."""

    global _probe_cache
    now = time.time()
    if _probe_cache is not None and now - _probe_cache[0] < _PROBE_TTL_S:
        return _probe_cache[1]
    binary = claude_binary()
    if binary is None:
        state = "missing"
    else:
        state = _probe(binary)
    _probe_cache = (now, state)
    return state


def clear_claude_probe_cache() -> None:
    global _probe_cache
    _probe_cache = None


def _probe(binary: str) -> str:
    try:
        completed = subprocess.run(
            [binary, "auth", "status"],
            capture_output=True,
            timeout=_PROBE_TIMEOUT_S,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        data = json.loads(completed.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return "logged-out"
    if not data.get("loggedIn"):
        return "logged-out"
    method = str(data.get("authMethod") or "")
    if method in {"claude.ai", "oauth_token"}:
        return "ready"
    if method in {"api_key", "api_key_helper"}:
        return "api-key"
    return "logged-out"


def subscription_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """Drop an API key so Claude Code keeps the subscription login it already has."""

    env = dict(base if base is not None else os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def build_claude_command(binary: str, system: str, user: str, model: str) -> list[str]:
    chosen = model or "sonnet"
    return [
        binary,
        "--print",
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(SCHEMA, separators=(",", ":")),
        "--system-prompt",
        system,
        "--model",
        chosen,
        "--tools",
        "",
        "--safe-mode",
        "--no-session-persistence",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--no-chrome",
        "--permission-mode",
        "dontAsk",
        "--permission-prompts",
        "none",
        user,
    ]


def unwrap_claude_stdout(stdout: str) -> dict:
    payload = parse_json_object(stdout)
    if payload.get("is_error"):
        detail = str(payload.get("result") or payload.get("error") or "errore senza dettaglio")
        raise ProviderError(f"Claude Code ha restituito un errore: {detail[:240]}")
    structured = payload.get("structured_output")
    if isinstance(structured, dict):
        return structured
    result = payload.get("result")
    if isinstance(result, dict):
        return result
    if isinstance(result, str) and result.strip():
        return parse_json_object(result)
    if "new_keywords" in payload:
        return payload
    raise ProviderError("Claude Code ha risposto senza il JSON degli appunti.")


def _default_runner(args: list[str], cwd: str, env: dict[str, str]) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            env=env,
            capture_output=True,
            timeout=_TIMEOUT_S,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        raise TransportError("Timeout di Claude Code. Il passaggio non è stato ritentato.", retryable=False) from exc
    except OSError as exc:
        raise TransportError(f"Claude Code non è partito: {exc.__class__.__name__}") from exc
    return completed.returncode, completed.stdout or "", completed.stderr or ""


class ClaudeAccountProvider(LLMProvider):
    name = "claude-account"

    def __init__(self, runner: Runner | None = None, binary: str | None = None) -> None:
        self._runner = runner or _default_runner
        self._binary_override = binary

    async def complete_json(self, system: str, user: str, model: str) -> dict:
        binary = self._binary_override if self._binary_override is not None else claude_binary()
        if not binary:
            raise MissingCredentials("il programma claude", self.name)
        command = build_claude_command(binary, system, user, model)
        env = subscription_env()
        with tempfile.TemporaryDirectory(prefix="lectureai-claude-") as folder:
            code, stdout, stderr = await asyncio.to_thread(self._runner, command, folder, env)
        if code != 0:
            detail = (stderr or stdout).strip().replace("\n", " ")[:240]
            lowered = detail.casefold()
            if "login" in lowered or "not logged" in lowered or "sign in" in lowered:
                raise MissingCredentials("il login di Claude Code", self.name)
            if any(token in lowered for token in ("overloaded", "rate limit", "529", "429")):
                raise TransportError(f"Claude Code non disponibile: {detail}")
            raise ProviderError(f"Claude Code si è chiuso con codice {code}: {detail or 'nessun dettaglio'}")
        if not stdout.strip():
            raise ProviderError("Claude Code non ha stampato una risposta.")
        try:
            return unwrap_claude_stdout(stdout)
        except (ProviderError, json.JSONDecodeError, ValueError) as exc:
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError("Risposta non interpretabile da Claude Code.") from exc
