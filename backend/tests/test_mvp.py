"""Offline checks. They never call a model provider."""

from __future__ import annotations

import asyncio
import json
import os
import unittest

os.environ.setdefault("LECTUREAI_DISABLE_TICKER", "1")

from fastapi.testclient import TestClient

from app.main import app
from app.models import KeywordIn, SlidePage
from app.services.graph_manager import GraphManager
from app.services.providers.base import MissingCredentials
from app.services.providers.demo import DemoProvider
from app.services.session_manager import sessions
from app.services.slides import extract_slides, match_terms

PASSAGE = (
    "La retropropagazione calcola il gradiente della funzione di perdita strato per strato. "
    "Il tasso di apprendimento decide l'ampiezza del passo lungo la discesa del gradiente."
)


class GraphTests(unittest.TestCase):
    def test_merge_adds_edge_once_and_keeps_importance(self) -> None:
        graph = GraphManager()
        nodes, edges = graph.apply_keywords(
            [
                KeywordIn(term="Gradiente", related_to=["Perdita"], importance=4),
                KeywordIn(term="Perdita", related_to=["Gradiente"], importance=3),
            ]
        )
        self.assertEqual(len(nodes), 2)
        self.assertEqual(len(edges), 1)

        again, new_edges = graph.apply_keywords(
            [KeywordIn(term="gradiente", related_to=["Perdita"], importance=2)]
        )
        self.assertEqual(again, [])
        self.assertEqual(new_edges, [])
        self.assertEqual(graph.nodes["gradiente"].importance, 4)

        added, linked = graph.apply_keywords(
            [
                KeywordIn(term="Gradiente", related_to=["Retropropagazione"], importance=5),
                KeywordIn(term="Retropropagazione", related_to=[], importance=4),
            ]
        )
        self.assertEqual([node.term for node in added], ["Retropropagazione"])
        self.assertEqual(len(linked), 1)
        self.assertEqual(graph.nodes["gradiente"].importance, 5)

    def test_explanation_attaches_to_existing_term(self) -> None:
        graph = GraphManager()
        graph.apply_keywords([KeywordIn(term="Perdita", related_to=[], importance=2)])
        node = graph.set_explanation("perdita", "Misura quanto la previsione si discosta dall'etichetta.")
        self.assertIsNotNone(node)
        assert node is not None
        self.assertEqual(node.id, "perdita")
        self.assertIn("previsione", node.explanation or "")


class SlideTests(unittest.TestCase):
    def test_matches_the_page_that_names_the_concept(self) -> None:
        pages = [
            SlidePage(number=1, title="Introduzione al corso", text="Benvenuti alla lezione di oggi sul programma."),
            SlidePage(
                number=2,
                title="Discesa del gradiente",
                text="La discesa del gradiente aggiorna i pesi della rete usando il gradiente della perdita.",
            ),
        ]
        matches = match_terms(pages, ["gradiente"])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].slide_number, 2)

    def test_invalid_pdf_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            extract_slides(b"this is not a pdf")


class DemoFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["LECTUREAI_DISABLE_TICKER"] = "1"
        sessions.reset()

    def tearDown(self) -> None:
        sessions.reset()

    def test_demo_provider_schema(self) -> None:
        raw = asyncio.run(
            DemoProvider().complete_json(
                "ignored",
                '{"language":"it","new_chunk":"%s","existing_keywords":[]}' % PASSAGE,
                "heuristic",
            )
        )
        self.assertTrue(raw["new_keywords"])
        self.assertTrue(raw["questions"])
        self.assertNotIn("riassume", raw["questions"][0].casefold())

    def test_session_analysis_builds_graph_without_network(self) -> None:
        session = sessions.create("demo", "heuristic", "it")
        session.transcript_parts.append(PASSAGE)
        session.pending = PASSAGE
        asyncio.run(sessions.analyze_now(session))
        self.assertGreaterEqual(len(session.graph.nodes), 1)
        self.assertGreaterEqual(len(session.questions), 1)

    def test_http_catalog_and_socket_snapshot(self) -> None:
        client = TestClient(app)
        health = client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        catalog = client.get("/api/providers")
        self.assertEqual(catalog.status_code, 200)
        ids = {item["id"] for item in catalog.json()["providers"]}
        self.assertIn("xai", ids)
        self.assertIn("demo", ids)
        self.assertNotIn("api_key", catalog.text)

        rejected = client.post("/api/sessions", json={"provider": "nope"})
        self.assertEqual(rejected.status_code, 400)

        created = client.post("/api/sessions", json={"provider": "demo", "model": "heuristic", "language": "it"})
        self.assertEqual(created.status_code, 200)
        session_id = created.json()["id"]
        with client.websocket_connect(f"/ws/sessions/{session_id}") as socket:
            snapshot = socket.receive_json()
            self.assertEqual(snapshot["type"], "snapshot")
            self.assertEqual(snapshot["session_id"], session_id)
        client.close()

    def test_missing_model_key_does_not_call_network(self) -> None:
        from app.services.providers.xai import XAIProvider

        provider = XAIProvider()
        if provider.api_key:
            self.skipTest("XAI_API_KEY is set in this environment")
        with self.assertRaises(MissingCredentials):
            asyncio.run(provider.complete_json("system", "user", "grok-4.7"))


class AnalysisGateTests(unittest.TestCase):
    def tearDown(self) -> None:
        sessions.reset()

    def test_opening_hook_does_not_trigger_the_first_pass(self) -> None:
        from app.config import ANALYSIS_FIRST_CHARS

        session = sessions.create("demo", "heuristic", "en")
        session.pending = "you are on a rock floating in space"
        self.assertFalse(sessions._due(session))
        session.pending = "cell " * ANALYSIS_FIRST_CHARS
        self.assertTrue(sessions._due(session))

    def test_unconfigured_default_uses_a_ready_account(self) -> None:
        from app.config import prefer_ready_provider

        chosen = prefer_ready_provider(
            "xai",
            {"xai": False, "grok-account": True, "claude-account": True},
        )
        self.assertEqual(chosen, "grok-account")
        self.assertEqual(prefer_ready_provider("claude-account", {"claude-account": True}), "claude-account")


class LocalSpeechTests(unittest.TestCase):
    def test_video_audio_becomes_text_without_loading_a_model(self) -> None:
        from app.services.stt import LocalWhisperSTT

        seen: list[tuple[int, str | None]] = []

        def transcribe(pcm: bytes, language: str | None) -> tuple[str, str | None, float]:
            seen.append((len(pcm), language))
            return "  il gradiente scende  ", None, 0.2

        engine = LocalWhisperSTT(
            transcribe=transcribe,
            chunk_seconds=0.05,
            min_seconds=0.02,
            idle_seconds=0.05,
        )
        lines: list[str] = []

        async def on_text(text: str, final: bool) -> None:
            self.assertTrue(final)
            lines.append(text)

        async def run() -> None:
            await engine.start(on_text)
            await engine.push_audio(b"\x01\x00" * 800)
            await engine.stop()

        asyncio.run(run())
        self.assertEqual(lines, ["il gradiente scende"])
        self.assertIsNone(seen[0][1])
        self.assertGreater(seen[0][0], 1000)

    def test_spoken_language_locks_after_a_confident_chunk(self) -> None:
        from app.services.stt import LocalWhisperSTT

        seen: list[str | None] = []

        def transcribe(pcm: bytes, language: str | None) -> tuple[str, str | None, float]:
            seen.append(language)
            return "cells divide", "en", 0.95

        engine = LocalWhisperSTT(transcribe=transcribe, chunk_seconds=0.05, min_seconds=0.02, idle_seconds=5)
        lines: list[str] = []

        async def on_text(text: str, final: bool) -> None:
            lines.append(text)

        async def run() -> None:
            await engine.start(on_text)
            await engine.push_audio(b"\x01\x00" * 800)
            for _ in range(30):
                if lines:
                    break
                await asyncio.sleep(0.02)
            await engine.push_audio(b"\x01\x00" * 800)
            for _ in range(30):
                if len(lines) >= 2:
                    break
                await asyncio.sleep(0.02)
            await engine.stop()

        asyncio.run(run())
        self.assertEqual(seen[0], None)
        self.assertEqual(seen[1], "en")

    def test_catalog_offers_local_transcription(self) -> None:
        import importlib.util

        client = TestClient(app)
        catalog = client.get("/api/providers")
        client.close()
        ready = importlib.util.find_spec("faster_whisper") is not None
        self.assertEqual(catalog.json()["stt"]["local"], ready)


class GrokAccountTests(unittest.TestCase):
    def test_command_uses_the_login_and_stays_out_of_the_repo(self) -> None:
        from app.services.providers.grok_account import GrokAccountProvider

        seen: dict = {}
        previous = os.environ.get("XAI_API_KEY")
        os.environ["XAI_API_KEY"] = "should-not-leak"

        def runner(args: list[str], cwd: str, env: dict[str, str]) -> tuple[int, str, str]:
            seen["args"] = args
            seen["cwd"] = cwd
            seen["env"] = env
            body = {
                "text": json.dumps(
                    {
                        "new_keywords": [{"term": "Gradiente", "related_to": ["Perdita"], "importance": 4}],
                        "questions": ["Perché il passo dipende dal tasso?"],
                        "expansions": [],
                        "slide_hints": [],
                    }
                ),
                "stopReason": "end_turn",
            }
            return 0, json.dumps(body), ""

        try:
            provider = GrokAccountProvider(runner=runner, binary="grok")
            raw = asyncio.run(provider.complete_json("sistema", '{"new_chunk":"tasso"}', "grok-4.7"))
        finally:
            if previous is None:
                os.environ.pop("XAI_API_KEY", None)
            else:
                os.environ["XAI_API_KEY"] = previous

        self.assertEqual(raw["new_keywords"][0]["term"], "Gradiente")
        args = seen["args"]
        self.assertEqual(args[0], "grok")
        self.assertEqual(args[1], "-p")
        self.assertEqual(args[2], '{"new_chunk":"tasso"}')
        self.assertEqual(args[args.index("--output-format") + 1], "json")
        self.assertIn("--json-schema", args)
        self.assertIn("--system-prompt-override", args)
        self.assertEqual(args[args.index("--max-turns") + 1], "1")
        self.assertIn("--no-plan", args)
        self.assertIn("--no-subagents", args)
        self.assertIn("--disable-web-search", args)
        self.assertEqual(args[args.index("--permission-mode") + 1], "dontAsk")
        self.assertNotIn("--tools", args)
        denied = args[args.index("--disallowed-tools") + 1]
        self.assertIn("run_terminal_cmd", denied)
        self.assertIn("web_search", denied)
        self.assertEqual(args[args.index("--cwd") + 1], seen["cwd"])
        self.assertNotIn("Assisted_Learning", seen["cwd"])
        self.assertNotIn("XAI_API_KEY", seen["env"])
        self.assertEqual(seen["env"].get("GROK_MEMORY"), "0")

    def test_structured_output_and_missing_binary(self) -> None:
        from app.services.providers.base import MissingCredentials
        from app.services.providers.grok_account import GrokAccountProvider, unwrap_grok_stdout

        parsed = unwrap_grok_stdout(
            json.dumps(
                {
                    "structured_output": {
                        "new_keywords": [],
                        "questions": [],
                        "expansions": [],
                        "slide_hints": [],
                    }
                }
            )
        )
        self.assertEqual(parsed["questions"], [])

        def runner(args: list[str], cwd: str, env: dict[str, str]) -> tuple[int, str, str]:
            raise AssertionError("il processo non doveva partire")

        provider = GrokAccountProvider(runner=runner, binary="")
        with self.assertRaises(MissingCredentials):
            asyncio.run(provider.complete_json("sistema", "utente", "grok-4.7"))

    def test_catalog_lists_the_account_provider(self) -> None:
        from app.services.providers.grok_account import clear_grok_probe_cache

        clear_grok_probe_cache()
        client = TestClient(app)
        catalog = client.get("/api/providers")
        client.close()
        found = next(item for item in catalog.json()["providers"] if item["id"] == "grok-account")
        self.assertEqual(found["via"], "cli")
        self.assertIn("grok-4.7", found["models"])
        self.assertNotIn("api_key", json.dumps(found))
        self.assertNotIn("auth.json", json.dumps(found))


class ClaudeAccountTests(unittest.TestCase):
    def test_command_uses_subscription_and_stays_out_of_the_repo(self) -> None:
        from app.services.providers.claude_account import ClaudeAccountProvider

        seen: dict = {}

        def runner(args: list[str], cwd: str, env: dict[str, str]) -> tuple[int, str, str]:
            seen["args"] = args
            seen["cwd"] = cwd
            seen["env"] = env
            body = {
                "type": "result",
                "is_error": False,
                "structured_output": {
                    "new_keywords": [{"term": "Gradiente", "related_to": ["Perdita"], "importance": 4}],
                    "questions": ["Perché il passo dipende dal tasso?"],
                    "expansions": [],
                    "slide_hints": [],
                },
            }
            return 0, json.dumps(body), ""

        provider = ClaudeAccountProvider(runner=runner, binary="claude")
        raw = asyncio.run(
            provider.complete_json(
                "sistema",
                '{"new_chunk":"tasso"}',
                "sonnet",
            )
        )
        self.assertEqual(raw["new_keywords"][0]["term"], "Gradiente")
        args = seen["args"]
        self.assertEqual(args[0], "claude")
        self.assertIn("--print", args)
        self.assertIn("--safe-mode", args)
        self.assertEqual(args[args.index("--tools") + 1], "")
        self.assertEqual(args[-1], '{"new_chunk":"tasso"}')
        self.assertNotIn("ANTHROPIC_API_KEY", seen["env"])
        self.assertTrue(seen["cwd"])
        self.assertNotIn("Assisted_Learning", seen["cwd"])

    def test_missing_binary_does_not_spawn(self) -> None:
        from app.services.providers.base import MissingCredentials
        from app.services.providers.claude_account import ClaudeAccountProvider

        def runner(args: list[str], cwd: str, env: dict[str, str]) -> tuple[int, str, str]:
            raise AssertionError("il processo non doveva partire")

        provider = ClaudeAccountProvider(runner=runner, binary="")
        with self.assertRaises(MissingCredentials):
            asyncio.run(provider.complete_json("sistema", "utente", "sonnet"))

    def test_catalog_lists_the_account_provider(self) -> None:
        from app.services.providers.claude_account import clear_claude_probe_cache

        clear_claude_probe_cache()
        client = TestClient(app)
        catalog = client.get("/api/providers")
        client.close()
        found = next(item for item in catalog.json()["providers"] if item["id"] == "claude-account")
        self.assertEqual(found["via"], "cli")
        self.assertIn("sonnet", found["models"])
        self.assertNotIn("api_key", json.dumps(found))


if __name__ == "__main__":
    unittest.main()
