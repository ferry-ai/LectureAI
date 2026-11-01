"""Turns a transcript chunk plus the current graph into a validated lecture delta.

The provider adapter only returns JSON. This module decides which provider to
call, retries a broken channel once, and asks once more when the shape is wrong.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.models import Expansion, LlmDelta, Question
from app.services.providers import get_provider
from app.services.providers.base import MissingCredentials, ProviderError, TransportError
from app.services.slides import match_hints

SYSTEM_PROMPT = """Sei il motore di LectureAI. Segui una lezione in tempo reale e aggiorni gli appunti dello studente.
Rispondi solo con un oggetto JSON valido, senza markdown e senza testo extra.
Schema:
{"new_keywords":[{"term":"string","related_to":["string"],"importance":1}],"questions":["string"],"expansions":[{"term":"string","explanation":"string"}],"slide_hints":[{"concept":"string","possible_slide_topic":"string"}]}
Regole:
- Usa la lingua del campo language.
- Non ripetere keyword già presenti in existing_keywords, a meno di aggiungere una relazione nuova e utile in related_to.
- importance è un intero da 1 a 5. Usa 5 solo per il concetto centrale del passaggio.
- Al massimo 4 new_keywords, 2 questions, 2 expansions, 2 slide_hints.
- Le domande verificano la comprensione (perché, confronto, conseguenza, errore tipico), non ripetono la frase appena detta.
- Mantieni i termini tecnici precisi. Non inventare contenuti assenti da new_chunk o da context_tail.
- Un aneddoto, una metafora o una frase di apertura non sono la materia. Non creare keyword per le parole di quella scena.
- Se da new_chunk e context_tail non si capisce ancora l'argomento della lezione, restituisci liste vuote.
- related_to cita termini già nel grafo oppure termini di questa stessa risposta.
- expansions: 2-3 frasi chiare, per chi ha perso il passaggio.
- slide_hints: concept è un termine del passaggio, possible_slide_topic è un titolo verosimile di slide.
- Se il passaggio non aggiunge nulla, restituisci liste vuote.
"""

_REMINDER = (
    "\n\nLa risposta precedente non era JSON valido rispetto allo schema. "
    "Restituisci solo l'oggetto JSON richiesto."
)


async def analyze(session: Any, chunk: str) -> dict:
    user = _user_payload(session, chunk)
    provider_name = session.provider
    source = "demo" if provider_name == "demo" else "llm"
    notice = None
    try:
        delta = await _produce(get_provider(provider_name), user, session.model)
        if source == "llm":
            session.notice = None
    except MissingCredentials as exc:
        if provider_name == "demo":
            raise
        notice = (
            f"Manca {exc.env_var} per {exc.provider}. "
            "Questo passaggio usa l'estrattore demo locale."
        )
        session.notice = notice
        delta = await _produce(get_provider("demo"), user, "heuristic")
        source = "demo"
    return _apply(session, delta, source)


async def _produce(provider, user: str, model: str) -> LlmDelta:
    last_error: Exception | None = None
    prompt = user
    for attempt in range(2):
        try:
            raw = await provider.complete_json(SYSTEM_PROMPT, prompt, model)
        except TransportError as exc:
            last_error = exc
            if exc.retryable and attempt == 0:
                continue
            raise
        try:
            return LlmDelta.model_validate(raw)
        except ValidationError as exc:
            last_error = exc
            prompt = user + _REMINDER
    raise ProviderError(f"JSON non valido da {provider.name}: {last_error}")


def _user_payload(session: Any, chunk: str) -> str:
    full = " ".join(session.transcript_parts)
    context = full[: -len(chunk)].strip() if full.endswith(chunk) else full
    outline = [
        {"page": page.number, "title": page.title, "excerpt": page.text[:180]}
        for page in session.slides[:12]
    ]
    payload = {
        "instruction": "Estrai solo il delta del new_chunk.",
        "language": session.language,
        "new_chunk": chunk,
        "context_tail": context[-1200:],
        "existing_keywords": session.graph.prompt_view(),
        "recent_questions": [question.text for question in session.questions[-6:]],
        "slide_outline": outline,
    }
    return json.dumps(payload, ensure_ascii=False)


def _apply(session: Any, delta: LlmDelta, source: str) -> dict:
    import time
    import uuid

    added_nodes, added_edges = session.graph.apply_keywords(delta.new_keywords)
    added_questions: list[Question] = []
    seen = {question.text.casefold() for question in session.questions}
    now = time.time()
    for text in delta.questions:
        if text.casefold() in seen:
            continue
        question = Question(id=uuid.uuid4().hex[:10], text=text, created_at=now)
        session.questions.append(question)
        seen.add(text.casefold())
        added_questions.append(question)
    session.questions = session.questions[-30:]

    added_expansions: list[Expansion] = []
    for item in delta.expansions:
        node = session.graph.set_explanation(item.term, item.explanation)
        if node is None or not node.explanation:
            continue
        expansion = Expansion(term=node.term, explanation=node.explanation)
        session.expansions[node.term.casefold()] = expansion
        added_expansions.append(expansion)

    fresh_matches = match_hints(session.slides, delta.slide_hints)
    if fresh_matches:
        merged = {(match.concept.casefold(), match.slide_number): match for match in session.slide_matches}
        for match in fresh_matches:
            merged[(match.concept.casefold(), match.slide_number)] = match
        session.slide_matches = sorted(merged.values(), key=lambda item: item.score, reverse=True)[:10]

    changed = any((added_nodes, added_edges, added_questions, added_expansions, fresh_matches))
    return {
        "type": "update",
        "source": source,
        "changed": changed,
        "notice": session.notice,
        "delta": {
            "keywords": [node.model_dump() for node in added_nodes],
            "edges": [edge.model_dump() for edge in added_edges],
            "questions": [question.model_dump() for question in added_questions],
            "expansions": [item.model_dump() for item in added_expansions],
            "slide_matches": [match.model_dump() for match in fresh_matches],
        },
        "graph": session.graph.snapshot(),
        "questions": [question.model_dump() for question in session.questions],
        "expansions": [item.model_dump() for item in session.expansions.values()],
        "slide_matches": [match.model_dump() for match in session.slide_matches],
    }
