"""Speech-to-text.

Deepgram is used for the microphone when DEEPGRAM_API_KEY is set.
A downloaded video sends the same 16 kHz PCM to a local Whisper model, so the
user does not provide a subtitle file. Audio stays in memory for the recording.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import threading
import time
from collections.abc import Awaitable, Callable

from app.config import DEEPGRAM_API_KEY
from app.services.providers.base import MissingCredentials

TranscriptCallback = Callable[[str, bool], Awaitable[None]]
ErrorCallback = Callable[[str], Awaitable[None]]
# pcm, locked spoken language or None while still detecting → text, detected language, probability
TranscribeFn = Callable[[bytes, str | None], tuple[str, str | None, float]]

_SAMPLE_RATE = 16_000
_MODEL = None
_MODEL_LOCK = threading.Lock()


class DeepgramSTT:
    def __init__(self, language: str = "it") -> None:
        self.language = language.split("-")[0] or "it"
        self._socket = None
        self._listener = None

    async def start(self, on_transcript: TranscriptCallback) -> None:
        if not DEEPGRAM_API_KEY:
            raise MissingCredentials("DEEPGRAM_API_KEY", "Deepgram")
        import websockets

        url = (
            "wss://api.deepgram.com/v1/listen"
            f"?model=nova-3&language={self.language}&punctuate=true&smart_format=true"
            "&interim_results=true&encoding=linear16&sample_rate=16000&channels=1&endpointing=400"
        )
        headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
        parameters = inspect.signature(websockets.connect).parameters
        header_kw = "additional_headers" if "additional_headers" in parameters else "extra_headers"
        self._socket = await websockets.connect(url, **{header_kw: headers})
        import asyncio

        self._listener = asyncio.create_task(self._listen(on_transcript))

    async def push_audio(self, chunk: bytes) -> None:
        if self._socket is None or not chunk:
            return
        await self._socket.send(chunk)

    async def stop(self) -> None:
        socket = self._socket
        listener = self._listener
        self._socket = None
        self._listener = None
        if socket is not None:
            try:
                await socket.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass
            await socket.close()
        if listener is not None:
            listener.cancel()

    async def _listen(self, on_transcript: TranscriptCallback) -> None:
        socket = self._socket
        if socket is None:
            return
        try:
            async for raw in socket:
                if isinstance(raw, bytes):
                    continue
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                alternatives = message.get("channel", {}).get("alternatives") or [{}]
                text = str(alternatives[0].get("transcript") or "").strip()
                if not text:
                    continue
                await on_transcript(text, bool(message.get("is_final")))
        except Exception:
            return


def local_model_loaded() -> bool:
    return _MODEL is not None


def whisper_transcribe_pcm(pcm: bytes, language: str | None) -> tuple[str, str | None, float]:
    """Transcribe one in-memory PCM chunk. None detects the spoken language."""

    if len(pcm) < 2:
        return "", None, 0.0
    if len(pcm) % 2:
        pcm = pcm[:-1]
    import numpy as np

    audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    options: dict = {
        "task": "transcribe",
        "vad_filter": True,
        "beam_size": 1,
        "condition_on_previous_text": False,
        "without_timestamps": True,
    }
    if language:
        options["language"] = language
    segments, info = _load_model().transcribe(audio, **options)
    parts: list[str] = []
    for segment in segments:
        if float(getattr(segment, "no_speech_prob", 0) or 0) > 0.6:
            continue
        text = str(getattr(segment, "text", "") or "").strip()
        if text:
            parts.append(text)
    detected = str(getattr(info, "language", "") or "").split("-")[0] or None
    probability = float(getattr(info, "language_probability", 0) or 0)
    return " ".join(parts), detected, probability


def _load_model():
    global _MODEL
    with _MODEL_LOCK:
        if _MODEL is None:
            from faster_whisper import WhisperModel

            _MODEL = WhisperModel("base", device="cpu", compute_type="int8")
        return _MODEL


class LocalWhisperSTT:
    """Turn playback PCM into final transcript lines. Nothing is written to disk."""

    def __init__(
        self,
        transcribe: TranscribeFn | None = None,
        chunk_seconds: float = 6,
        min_seconds: float = 0.8,
        idle_seconds: float = 1.2,
    ) -> None:
        # Spoken language is detected from the audio. The notes language stays separate.
        self._spoken: str | None = None
        self._transcribe = transcribe or whisper_transcribe_pcm
        self._chunk_bytes = max(2, int(_SAMPLE_RATE * 2 * chunk_seconds))
        self._min_bytes = max(2, int(_SAMPLE_RATE * 2 * min_seconds))
        self._idle_s = idle_seconds
        self._buffer = bytearray()
        self._last_audio = 0.0
        self._stopped = False
        self._reported = False
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._on_transcript: TranscriptCallback | None = None
        self._on_error: ErrorCallback | None = None

    async def start(self, on_transcript: TranscriptCallback, on_error: ErrorCallback | None = None) -> None:
        self._on_transcript = on_transcript
        self._on_error = on_error
        self._stopped = False
        self._task = asyncio.create_task(self._pump())

    async def push_audio(self, chunk: bytes) -> None:
        if self._stopped or not chunk:
            return
        self._buffer.extend(chunk)
        self._last_audio = time.monotonic()
        self._wake.set()

    async def stop(self) -> None:
        self._stopped = True
        self._wake.set()
        task = self._task
        self._task = None
        if task is not None:
            await task

    async def _pump(self) -> None:
        while not self._stopped:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=0.3)
            except TimeoutError:
                pass
            self._wake.clear()
            await self._drain(force=False)
        await self._drain(force=True)

    async def _drain(self, force: bool) -> None:
        idle = self._last_audio > 0 and time.monotonic() - self._last_audio >= self._idle_s
        if force:
            take = len(self._buffer)
        elif len(self._buffer) >= self._chunk_bytes:
            take = self._chunk_bytes
        elif idle and len(self._buffer) >= self._min_bytes:
            take = len(self._buffer)
        else:
            return
        if take < 2:
            return
        if take % 2:
            take -= 1
        pcm = bytes(self._buffer[:take])
        del self._buffer[:take]
        try:
            text, detected, probability = await asyncio.to_thread(self._transcribe, pcm, self._spoken)
        except Exception as exc:
            await self._report(f"Trascrizione del video non disponibile: {exc.__class__.__name__}.")
            return
        if self._spoken is None and detected and probability >= 0.7:
            self._spoken = detected
        text = " ".join(text.split())
        if text and self._on_transcript is not None:
            await self._on_transcript(text, True)

    async def _report(self, message: str) -> None:
        if self._reported or self._on_error is None:
            return
        self._reported = True
        await self._on_error(message)
