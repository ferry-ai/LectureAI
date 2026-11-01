"""Session HTTP routes and the lecture WebSocket."""

from __future__ import annotations

import json

from fastapi import APIRouter, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect

from app.config import provider_catalog
from app.models import CreateSessionBody
from app.services.providers.base import MissingCredentials
from app.services.session_manager import LectureSession, sessions

router = APIRouter()
_MAX_PDF = 20 * 1024 * 1024


def _session(session_id: str) -> LectureSession:
    try:
        return sessions.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Sessione non trovata.") from None


@router.get("/api/providers")
async def providers() -> dict:
    return provider_catalog()


@router.post("/api/sessions")
async def create_session(body: CreateSessionBody) -> dict:
    try:
        session = sessions.create(body.provider, body.model, body.language)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sessions.start_ticker(session)
    return session.public()


@router.get("/api/sessions/{session_id}")
async def read_session(session_id: str) -> dict:
    session = _session(session_id)
    return sessions.snapshot_message(session)


@router.post("/api/sessions/{session_id}/slides")
async def upload_slides(session_id: str, file: UploadFile = File(...)) -> dict:
    session = _session(session_id)
    name = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()
    if not name.endswith(".pdf") and "pdf" not in content_type:
        raise HTTPException(status_code=400, detail="Carica un PDF.")
    data = await file.read()
    if len(data) > _MAX_PDF:
        raise HTTPException(status_code=413, detail="PDF oltre 20 MB.")
    try:
        payload = await sessions.set_slides(session, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return payload


@router.websocket("/ws/sessions/{session_id}")
async def session_socket(websocket: WebSocket, session_id: str) -> None:
    try:
        session = sessions.get(session_id)
    except KeyError:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    session.clients.add(websocket)
    await websocket.send_json(sessions.snapshot_message(session))
    try:
        while True:
            incoming = await websocket.receive()
            if incoming["type"] == "websocket.disconnect":
                break
            if incoming.get("bytes") is not None:
                await sessions.push_audio(session, incoming["bytes"])
                continue
            raw = incoming.get("text")
            if not raw:
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "scope": "client", "message": "JSON non valido."})
                continue
            await _handle(session, message)
    except WebSocketDisconnect:
        pass
    finally:
        session.clients.discard(websocket)
        if not session.clients:
            await sessions.stop_stt(session)


async def _handle(session: LectureSession, message: dict) -> None:
    kind = str(message.get("type") or "")
    try:
        if kind == "config":
            sessions.configure(
                session,
                message.get("provider"),
                message.get("model"),
                message.get("language"),
            )
            await sessions.broadcast(
                session,
                {
                    "type": "status",
                    "provider": session.provider,
                    "model": session.model,
                    "language": session.language,
                },
            )
        elif kind == "transcript":
            await sessions.add_transcript(session, str(message.get("text") or ""), bool(message.get("final")))
        elif kind == "analyze":
            await sessions.analyze_now(session)
        elif kind == "start":
            await sessions.start_stt(session, str(message.get("stt") or "browser"))
        elif kind == "stop":
            await sessions.stop_stt(session)
            await sessions.broadcast(session, {"type": "status", "recording": False})
            if session.pending.strip():
                await sessions.analyze_now(session)
        else:
            await sessions.broadcast(session, {"type": "error", "scope": "client", "message": "Messaggio sconosciuto."})
    except MissingCredentials as exc:
        await sessions.broadcast(
            session,
            {
                "type": "error",
                "scope": "stt",
                "message": f"Manca {exc.env_var}. Usa la trascrizione del browser.",
            },
        )
    except ValueError as exc:
        await sessions.broadcast(session, {"type": "error", "scope": "client", "message": str(exc)})
