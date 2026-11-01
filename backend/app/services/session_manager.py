"""In-memory lecture sessions. Audio is not stored; only transcript, graph and slides."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field

from fastapi import WebSocket

from app.config import (
    ANALYSIS_FIRST_CHARS,
    ANALYSIS_MIN_CHARS,
    ANALYSIS_MIN_INTERVAL,
    clean_language,
    clean_model,
    clean_provider,
)
from app.models import Expansion, Question, SlideMatch, SlidePage
from app.services.graph_manager import GraphManager
from app.services.llm_orchestrator import analyze
from app.services.slides import extract_slides, match_terms
from app.services.stt import DeepgramSTT, LocalWhisperSTT, local_model_loaded

_TRANSCRIPT_CAP = 200_000


@dataclass
class LectureSession:
    id: str
    provider: str
    model: str
    language: str
    graph: GraphManager = field(default_factory=GraphManager)
    questions: list[Question] = field(default_factory=list)
    expansions: dict[str, Expansion] = field(default_factory=dict)
    slides: list[SlidePage] = field(default_factory=list)
    slide_matches: list[SlideMatch] = field(default_factory=list)
    slide_warning: str | None = None
    transcript_parts: list[str] = field(default_factory=list)
    pending: str = ""
    interim: str = ""
    recording: bool = False
    stt_mode: str = "browser"
    notice: str | None = None
    last_analysis_at: float = 0
    closed: bool = False
    analysis_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    clients: set[WebSocket] = field(default_factory=set)
    speech: DeepgramSTT | LocalWhisperSTT | None = None
    analysis_task: asyncio.Task | None = None
    ticker: asyncio.Task | None = None

    def public(self) -> dict:
        return {
            "id": self.id,
            "provider": self.provider,
            "model": self.model,
            "language": self.language,
            "slide_count": len(self.slides),
            "slide_warning": self.slide_warning,
        }

    def transcript_tail(self) -> str:
        return " ".join(self.transcript_parts)[-1800:]


class SessionManager:
    def __init__(self) -> None:
        self._items: dict[str, LectureSession] = {}

    def create(self, provider: str, model: str, language: str) -> LectureSession:
        chosen = clean_provider(provider)
        session = LectureSession(
            id=uuid.uuid4().hex,
            provider=chosen,
            model=clean_model(model, chosen),
            language=clean_language(language),
        )
        self._items[session.id] = session
        return session

    def get(self, session_id: str) -> LectureSession:
        try:
            return self._items[session_id]
        except KeyError as exc:
            raise KeyError(session_id) from exc

    def reset(self) -> None:
        for session in list(self._items.values()):
            session.closed = True
            for task in (session.ticker, session.analysis_task):
                if task is not None and not task.done():
                    task.cancel()
        self._items.clear()

    def start_ticker(self, session: LectureSession) -> None:
        if os.getenv("LECTUREAI_DISABLE_TICKER") == "1" or session.ticker is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        session.ticker = loop.create_task(self._ticker(session))

    def configure(self, session: LectureSession, provider: str | None, model: str | None, language: str | None) -> None:
        if provider:
            session.provider = clean_provider(provider)
        if model is not None or provider:
            session.model = clean_model(model or session.model, session.provider)
        if language:
            session.language = clean_language(language)

    async def add_transcript(self, session: LectureSession, text: str, final: bool) -> None:
        text = " ".join(text.split())
        if not text:
            return
        if final:
            session.transcript_parts.append(text)
            self._trim(session)
            session.pending = f"{session.pending} {text}".strip()
            session.interim = ""
        else:
            session.interim = text
        await self.broadcast(
            session,
            {
                "type": "transcript",
                "final": final,
                "text": text,
                "tail": session.transcript_tail(),
                "interim": session.interim,
            },
        )
        if final:
            self.schedule(session)

    def schedule(self, session: LectureSession) -> None:
        task = session.analysis_task
        if task is not None and not task.done():
            return
        if not self._due(session):
            return
        session.analysis_task = asyncio.create_task(self._guarded(session))

    async def analyze_now(self, session: LectureSession) -> None:
        await self._run(session, force=True)

    async def set_slides(self, session: LectureSession, data: bytes) -> dict:
        pages, warning = extract_slides(data)
        session.slides = pages
        session.slide_warning = warning
        terms = [node.term for node in session.graph.nodes.values()]
        session.slide_matches = match_terms(pages, terms)
        payload = {
            "type": "slides",
            "slide_count": len(pages),
            "slide_warning": warning,
            "slide_matches": [match.model_dump() for match in session.slide_matches],
        }
        await self.broadcast(session, payload)
        return payload

    async def start_stt(self, session: LectureSession, mode: str) -> None:
        await self.stop_stt(session)
        session.stt_mode = mode if mode in {"browser", "deepgram", "local", "demo"} else "browser"
        session.recording = True
        if session.stt_mode == "deepgram":
            engine: DeepgramSTT | LocalWhisperSTT = DeepgramSTT(language=session.language)
        elif session.stt_mode == "local":
            engine = LocalWhisperSTT()
            if not local_model_loaded():
                session.notice = (
                    "Trascrivo l'audio del video su questo PC. "
                    "La prima volta prepara un modello locale, poi il testo compare mentre guardi."
                )
                await self.broadcast(session, {"type": "notice", "message": session.notice})
        else:
            engine = None
        if engine is not None:

            async def on_text(text: str, final: bool) -> None:
                if session.notice and session.notice.startswith("Trascrivo l'audio del video"):
                    session.notice = None
                    await self.broadcast(session, {"type": "notice", "message": ""})
                await self.add_transcript(session, text, final)

            async def on_error(message: str) -> None:
                await self.broadcast(session, {"type": "error", "scope": "stt", "message": message})

            if isinstance(engine, LocalWhisperSTT):
                await engine.start(on_text, on_error)
            else:
                await engine.start(on_text)
            session.speech = engine
        await self.broadcast(session, {"type": "status", "recording": True, "stt": session.stt_mode})

    async def stop_stt(self, session: LectureSession) -> None:
        session.recording = False
        engine = session.speech
        session.speech = None
        if engine is not None:
            await engine.stop()

    async def push_audio(self, session: LectureSession, chunk: bytes) -> None:
        if session.speech is not None:
            await session.speech.push_audio(chunk)

    def snapshot_message(self, session: LectureSession) -> dict:
        return {
            "type": "snapshot",
            "session_id": session.id,
            "provider": session.provider,
            "model": session.model,
            "language": session.language,
            "graph": session.graph.snapshot(),
            "questions": [question.model_dump() for question in session.questions],
            "expansions": [item.model_dump() for item in session.expansions.values()],
            "slide_matches": [match.model_dump() for match in session.slide_matches],
            "slide_count": len(session.slides),
            "slide_warning": session.slide_warning,
            "transcript_tail": session.transcript_tail(),
            "interim": session.interim,
            "notice": session.notice,
            "stt": session.stt_mode,
        }

    async def broadcast(self, session: LectureSession, message: dict) -> None:
        payload = json.dumps(message, ensure_ascii=False)
        dead: list[WebSocket] = []
        for client in list(session.clients):
            try:
                await client.send_text(payload)
            except Exception:
                dead.append(client)
        for client in dead:
            session.clients.discard(client)

    def _due(self, session: LectureSession) -> bool:
        pending = session.pending.strip()
        if session.last_analysis_at <= 0:
            return len(pending) >= ANALYSIS_FIRST_CHARS
        if len(pending) < ANALYSIS_MIN_CHARS:
            return False
        return (time.time() - session.last_analysis_at) >= ANALYSIS_MIN_INTERVAL

    async def _guarded(self, session: LectureSession) -> None:
        try:
            await self._run(session, force=False)
        finally:
            session.analysis_task = None
            if not session.closed:
                self.schedule(session)

    async def _run(self, session: LectureSession, force: bool) -> None:
        async with session.analysis_lock:
            if session.closed:
                return
            if not force and not self._due(session):
                return
            chunk = session.pending.strip()
            if not chunk:
                if force:
                    await self.broadcast(session, {"type": "status", "analyzing": False, "idle": True})
                return
            session.pending = ""
            session.last_analysis_at = time.time()
            await self.broadcast(session, {"type": "status", "analyzing": True})
            try:
                update = await analyze(session, chunk)
            except Exception as exc:
                session.pending = f"{chunk} {session.pending}".strip()
                await self.broadcast(session, {"type": "status", "analyzing": False})
                await self.broadcast(
                    session,
                    {"type": "error", "scope": "llm", "message": str(exc)},
                )
                return
            await self.broadcast(session, {"type": "status", "analyzing": False})
            if update.get("changed") or update.get("notice"):
                await self.broadcast(session, update)

    async def _ticker(self, session: LectureSession) -> None:
        try:
            while not session.closed:
                await asyncio.sleep(5)
                self.schedule(session)
        except asyncio.CancelledError:
            return

    def _trim(self, session: LectureSession) -> None:
        while session.transcript_parts and sum(len(part) for part in session.transcript_parts) > _TRANSCRIPT_CAP:
            session.transcript_parts.pop(0)


sessions = SessionManager()
