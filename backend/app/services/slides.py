"""PDF text extraction and a lexical match against slide pages.

Scanned slides have no text layer. We say so instead of guessing.
"""

from __future__ import annotations

import re
from io import BytesIO

from pypdf import PdfReader

from app.models import SlideHintIn, SlideMatch, SlidePage
from app.textutil import collapse

_TOKEN = re.compile(r"[A-Za-zÀ-ÿ0-9]{4,}")
_STOP = frozenset(
    "della dello degli delle questo questa questi queste quello quella sono viene con per non tra fra come dove quando perché perche slide pagina".split()
)
_MAX_PAGES = 80


def extract_slides(data: bytes) -> tuple[list[SlidePage], str | None]:
    try:
        reader = PdfReader(BytesIO(data))
    except Exception as exc:
        raise ValueError("PDF non leggibile.") from exc

    pages: list[SlidePage] = []
    for index, page in enumerate(reader.pages, start=1):
        if index > _MAX_PAGES:
            break
        raw = page.extract_text() or ""
        text = collapse(raw.replace("\n", " "))
        title = text[:90] if text else f"Slide {index}"
        pages.append(SlidePage(number=index, title=title, text=text))

    warning = None
    if not pages:
        warning = "Il PDF non contiene pagine."
    elif all(not page.text for page in pages):
        warning = "Nessun testo estraibile: il PDF potrebbe essere una scansione."
    elif len(reader.pages) > _MAX_PAGES:
        warning = f"Analizzo solo le prime {_MAX_PAGES} pagine."
    return pages, warning


def match_hints(pages: list[SlidePage], hints: list[SlideHintIn], limit: int = 8) -> list[SlideMatch]:
    concepts = [(hint.concept, hint.possible_slide_topic) for hint in hints if hint.concept]
    return _match(pages, concepts, limit)


def match_terms(pages: list[SlidePage], terms: list[str], limit: int = 8) -> list[SlideMatch]:
    concepts = [(term, term) for term in terms if term.strip()]
    return _match(pages, concepts, limit)


def _match(pages: list[SlidePage], concepts: list[tuple[str, str]], limit: int) -> list[SlideMatch]:
    if not pages or not concepts:
        return []
    page_tokens = [(page, _tokens(page.text)) for page in pages]
    found: list[SlideMatch] = []
    seen: set[tuple[str, int]] = set()
    for concept, topic in concepts:
        query = _tokens(concept) | _tokens(topic)
        concept_tokens = _tokens(concept)
        if not query:
            continue
        best: SlideMatch | None = None
        for page, tokens in page_tokens:
            if not tokens:
                continue
            overlap = query & tokens
            if not overlap:
                continue
            score = len(overlap) / len(query)
            if concept_tokens and concept_tokens <= tokens:
                score += 0.25
            if score < 0.4:
                continue
            if best is None or score > best.score:
                best = SlideMatch(
                    concept=concept,
                    slide_number=page.number,
                    title=page.title,
                    excerpt=page.text[:180],
                    score=round(score, 3),
                )
        if best is None:
            continue
        key = (best.concept.casefold(), best.slide_number)
        if key in seen:
            continue
        seen.add(key)
        found.append(best)
    found.sort(key=lambda item: item.score, reverse=True)
    return found[:limit]


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in _TOKEN.findall(text) if token.casefold() not in _STOP}
