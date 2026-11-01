"""Lecture delta through the official Grok CLI already logged in on this PC.

LectureAI does not read ~/.grok/auth.json. It starts `grok -p` in an empty folder,
with tools removed, and reads the JSON the process prints. A session token in that
file takes precedence inside the CLI; this process still drops XAI_API_KEY so a
missing login cannot fall through to a console key.
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

# A lecture pass is one shot. 75s covers a slow reply; a timeout is not retried.
_TIMEOUT_S = 75
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

# An empty --tools value does not remove tools. Name every built-in the headless
# guide documents, on both the shell route and the daemon route.
_DENIED_TOOLS = ",".join(
    (
        "read_file",
        "grep",
        "list_dir",
        "web_search",
        "web_fetch",
        "write",
        "search_replace",
        "run_terminal_cmd",
        "run_terminal_command",
        "task",
        "spawn_subagent",
        "Agent",
        "get_task_output",
        "wait_tasks",
        "kill_task",
        "get_command_or_subagent_output",
        "wait_commands_or_subagents",
        "kill_command_or_subagent",
        "enter_plan_mode",
        "exit_plan_mode",
        "monitor",
        "workflow",
        "image_gen",
        "image_edit",
        "GenerateImage",
        "hashline_read",
        "hashline_grep",
        "hashline_edit",
        "StrReplace",
        "EditNotebook",
        "Delete",
        "Shell",
        "Await",
        "ReadLints",
        "SwitchMode",
        "AskQuestion",
        "CreatePlan",
        "CallMcpTool",
        "GetMcpTools",
        "FetchMcpResource",
        "ListMcpResources",
        "XSearch",
        "lsp",
        "TodoWrite",
        "scheduler_create",
        "scheduler_delete",
        "scheduler_list",
    )
)

Runner = Callable[[list[str], str, dict[str, str]], tuple[int, str, str]]

_probe_cache: tuple[float, str] | None = None


def grok_binary() -> str | None:
    override = os.getenv("LECTUREAI_GROK_BIN", "").strip()
    if override:
        return override if Path(override).is_file() else None
    found = shutil.which("grok")
    if found:
        return found
    candidate = Path.home() / ".grok" / "bin" / "grok.exe"
    return str(candidate) if candidate.is_file() else None


def _login_file_present() -> bool:
    """True when a login file exists. The contents are never read."""

    path = Path.home() / ".grok" / "auth.json"
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def grok_account_state() -> str:
    """ready, missing, or logged-out. Cached briefly so the catalog stays cheap."""

    global _probe_cache
    now = time.time()
    if _probe_cache is not None and now - _probe_cache[0] < _PROBE_TTL_S:
        return _probe_cache[1]
    if grok_binary() is None:
        state = "missing"
    elif _login_file_present():
        state = "ready"
    else:
        state = "logged-out"
    _probe_cache = (now, state)
    return state


def clear_grok_probe_cache() -> None:
    global _probe_cache
    _probe_cache = None


def account_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """Drop the console key so the CLI cannot bill it when the login is missing."""

    env = dict(base if base is not None else os.environ)
    env.pop("XAI_API_KEY", None)
    env["GROK_DISABLE_AUTOUPDATER"] = "1"
    env["GROK_MEMORY"] = "0"
    return env


def build_grok_command(binary: str, system: str, user: str, model: str, cwd: str) -> list[str]:
    chosen = model or "grok-4.7"
    return [
        binary,
        "-p",
        user,
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(SCHEMA, separators=(",", ":")),
        "--system-prompt-override",
        system,
        "--model",
        chosen,
        "--max-turns",
        "1",
        "--reasoning-effort",
        "low",
        "--no-plan",
        "--no-subagents",
        "--disable-web-search",
        "--permission-mode",
        "dontAsk",
        "--disallowed-tools",
        _DENIED_TOOLS,
        "--cwd",
        cwd,
    ]


def unwrap_grok_stdout(stdout: str) -> dict:
    payload = parse_json_object(stdout)
    if payload.get("type") == "error" or payload.get("is_error"):
        detail = str(payload.get("message") or payload.get("result") or payload.get("error") or "errore senza dettaglio")
        raise ProviderError(f"Grok ha restituito un errore: {detail[:240]}")
    structured = payload.get("structured_output")
    if isinstance(structured, dict):
        return structured
    if isinstance(structured, str) and structured.strip():
        return parse_json_object(structured)
    text = payload.get("text")
    if isinstance(text, dict):
        return text
    if isinstance(text, str) and text.strip():
        return parse_json_object(text)
    result = payload.get("result")
    if isinstance(result, dict):
        return result
    if isinstance(result, str) and result.strip():
        return parse_json_object(result)
    if "new_keywords" in payload:
        return payload
    raise ProviderError("Grok ha risposto senza il JSON degli appunti.")


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
        raise TransportError("Timeout di Grok. Il passaggio non è stato ritentato.", retryable=False) from exc
    except OSError as exc:
        raise TransportError(f"Grok non è partito: {exc.__class__.__name__}") from exc
    return completed.returncode, completed.stdout or "", completed.stderr or ""


class GrokAccountProvider(LLMProvider):
    name = "grok-account"

    def __init__(self, runner: Runner | None = None, binary: str | None = None) -> None:
        self._runner = runner or _default_runner
        self._binary_override = binary

    async def complete_json(self, system: str, user: str, model: str) -> dict:
        binary = self._binary_override if self._binary_override is not None else grok_binary()
        if not binary:
            raise MissingCredentials("il programma grok", self.name)
        env = account_env()
        with tempfile.TemporaryDirectory(prefix="lectureai-grok-") as folder:
            command = build_grok_command(binary, system, user, model, folder)
            code, stdout, stderr = await asyncio.to_thread(self._runner, command, folder, env)
        if code != 0:
            detail = (stderr or stdout).strip().replace("\n", " ")[:240]
            lowered = detail.casefold()
            if any(token in lowered for token in ("login", "sign in", "not logged", "authenticate")):
                raise MissingCredentials("il login di Grok", self.name)
            if any(token in lowered for token in ("overloaded", "rate limit", "429", "503")):
                raise TransportError(f"Grok non disponibile: {detail}")
            raise ProviderError(f"Grok si è chiuso con codice {code}: {detail or 'nessun dettaglio'}")
        if not stdout.strip():
            raise ProviderError("Grok non ha stampato una risposta.")
        try:
            return unwrap_grok_stdout(stdout)
        except (ProviderError, json.JSONDecodeError, ValueError) as exc:
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError("Risposta non interpretabile da Grok.") from exc
