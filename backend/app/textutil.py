"""Small text helpers shared by the graph and the demo extractor."""

from __future__ import annotations

import re

_SPACE = re.compile(r"\s+")


def collapse(text: str) -> str:
    return _SPACE.sub(" ", text).strip()


def norm_term(text: str) -> str:
    return collapse(text).casefold()
