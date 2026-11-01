"""Local extractor used when no model key is configured, and for the demo lecture.

It does not invent textbook definitions. It pulls content words from the new
transcript chunk and writes comprehension questions from those terms.
"""

from __future__ import annotations

import json
import re

from app.services.providers.base import LLMProvider
from app.textutil import norm_term

_TOKEN = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'-]{3,}")

_STOP = frozenset(
    """
    oggi vediamo come una dall dalla dalle dagli dallo degli delle della dello
    dei del sul sui sulle sono viene vengono essere questo questa questi queste
    anche solo dopo prima ogni suoi sue loro hanno nel nella negli nelle con
    per che non tra fra dove quando perché perchè quindi oppure allora conviene
    troppo mentre quello quella quelli quelle più meno verso attraverso dai
    degli degli degli alla alle allo agli negli senza dentro fuori sopra sotto
    molto poco tanto quanto quale quali nostro nostra nostri vostro vostra
    essere stato stata stati state fare fatto dire detto usare usato possiamo
    potete dovete bisogna serve servono esempio proprio ancora sempre mai gia
    già cosi così qui qua gli una uno due tre the and with this that from into
    your their have been were they them than then just about over under
    """.split()
)


class DemoProvider(LLMProvider):
    name = "demo"

    async def complete_json(self, system: str, user: str, model: str) -> dict:
        del system, model
        try:
            payload = json.loads(user)
        except json.JSONDecodeError:
            payload = {"new_chunk": user, "language": "it", "existing_keywords": []}
        if not isinstance(payload, dict):
            payload = {"new_chunk": user, "language": "it", "existing_keywords": []}

        chunk = str(payload.get("new_chunk") or "")
        language = str(payload.get("language") or "it")
        existing = payload.get("existing_keywords") or []
        if not isinstance(existing, list):
            existing = []

        known = {}
        for item in existing:
            if isinstance(item, dict) and item.get("term"):
                known[norm_term(str(item["term"]))] = item

        phrases = _rank_phrases(chunk)
        fresh = [phrase for phrase in phrases if norm_term(phrase) not in known][:4]
        keywords = []
        for index, phrase in enumerate(fresh):
            related = [fresh[0]] if index else []
            for item in known.values():
                term = str(item.get("term") or "")
                already = {norm_term(rel) for rel in item.get("related_to") or [] if isinstance(rel, str)}
                if term and norm_term(term) in norm_term(chunk) and norm_term(phrase) not in already:
                    related.append(term)
                    break
            keywords.append(
                {
                    "term": phrase,
                    "related_to": related[:4],
                    "importance": 4 if index == 0 else 3,
                }
            )

        # A new link between two concepts already on the graph, if this chunk names both.
        if not keywords:
            mentioned = [
                item for item in known.values() if norm_term(str(item.get("term"))) in norm_term(chunk)
            ]
            if len(mentioned) >= 2:
                first = str(mentioned[0]["term"])
                second = str(mentioned[1]["term"])
                linked = {norm_term(rel) for rel in mentioned[0].get("related_to") or [] if isinstance(rel, str)}
                if norm_term(second) not in linked:
                    keywords.append({"term": first, "related_to": [second], "importance": 3})

        focus = fresh[0] if fresh else (str(keywords[0]["term"]) if keywords else "")
        other = fresh[1] if len(fresh) > 1 else ""
        questions = _questions(language, focus, other) if focus else []
        expansions = []
        if focus:
            sentence = _sentence_with(chunk, focus)
            expansions.append({"term": focus, "explanation": _explanation(language, focus, sentence)})

        hints = []
        for phrase in fresh[:2]:
            hints.append({"concept": phrase, "possible_slide_topic": phrase})

        return {
            "new_keywords": keywords,
            "questions": questions,
            "expansions": expansions,
            "slide_hints": hints,
        }


def _rank_phrases(chunk: str) -> list[str]:
    counts: dict[str, int] = {}
    order: dict[str, int] = {}
    display: dict[str, str] = {}
    for position, match in enumerate(_TOKEN.finditer(chunk)):
        word = match.group(0)
        key = norm_term(word)
        if key in _STOP or len(key) < 4:
            continue
        counts[key] = counts.get(key, 0) + 1
        order.setdefault(key, position)
        display.setdefault(key, word)
    ranked = sorted(counts, key=lambda key: (-(counts[key] * 10 + min(len(key), 24)), order[key]))
    return [display[key] for key in ranked]


def _sentence_with(chunk: str, term: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", chunk.strip())
    folded = norm_term(term)
    for part in parts:
        if folded in norm_term(part):
            return part.strip()
    return chunk.strip()[:280]


def _questions(language: str, focus: str, other: str) -> list[str]:
    if language.startswith("en"):
        questions = [f"Why does {focus} matter for the next step, not only for the sentence you just heard?"]
        if other:
            questions.append(f"What would change in {other} if {focus} were missing or mis-stated?")
        return questions
    questions = [f"Perché {focus} conta per il passaggio successivo, e non solo per la frase appena detta?"]
    if other:
        questions.append(f"Cosa cambierebbe in {other} se {focus} mancasse o fosse formulato male?")
    return questions


def _explanation(language: str, term: str, sentence: str) -> str:
    if language.startswith("en"):
        return (
            f"In this passage the lecturer introduces {term}. {sentence} "
            "Keep the technical term as it was said and connect it to the neighboring ideas on the graph."
        )
    return (
        f"In questo passaggio il docente introduce {term}. {sentence} "
        "Tieni il termine tecnico com'è stato detto e collegalo alle idee vicine nel grafo."
    )
