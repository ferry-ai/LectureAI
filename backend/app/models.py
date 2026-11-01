"""Shared schemas for the lecture delta, the graph, and session snapshots."""

from __future__ import annotations

import re

from pydantic import BaseModel, field_validator, model_validator


def _clean_line(value: object, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


class KeywordIn(BaseModel):
    term: str
    related_to: list[str] = []
    importance: int = 2

    @field_validator("term", mode="before")
    @classmethod
    def clean_term(cls, value: object) -> str:
        return _clean_line(value, 80)

    @field_validator("related_to", mode="before")
    @classmethod
    def clean_related(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        cleaned = [_clean_line(item, 80) for item in value]
        return [item for item in cleaned if item][:8]

    @field_validator("importance", mode="before")
    @classmethod
    def clamp_importance(cls, value: object) -> int:
        try:
            number = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            number = 2
        return max(1, min(5, number))


class ExpansionIn(BaseModel):
    term: str
    explanation: str

    @field_validator("term", mode="before")
    @classmethod
    def clean_term(cls, value: object) -> str:
        return _clean_line(value, 80)

    @field_validator("explanation", mode="before")
    @classmethod
    def clean_explanation(cls, value: object) -> str:
        return _clean_line(value, 800)


class SlideHintIn(BaseModel):
    concept: str
    possible_slide_topic: str

    @field_validator("concept", "possible_slide_topic", mode="before")
    @classmethod
    def clean(cls, value: object) -> str:
        return _clean_line(value, 120)


class LlmDelta(BaseModel):
    new_keywords: list[KeywordIn] = []
    questions: list[str] = []
    expansions: list[ExpansionIn] = []
    slide_hints: list[SlideHintIn] = []

    @field_validator("questions", mode="before")
    @classmethod
    def clean_questions(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        questions: list[str] = []
        for item in value:
            text = _clean_line(item, 240)
            if text:
                questions.append(text)
            if len(questions) == 3:
                break
        return questions

    @model_validator(mode="after")
    def cap_lists(self) -> "LlmDelta":
        self.new_keywords = [item for item in self.new_keywords if item.term][:6]
        self.expansions = [item for item in self.expansions if item.term and item.explanation][:3]
        self.slide_hints = [item for item in self.slide_hints if item.concept][:3]
        return self


class GraphNode(BaseModel):
    id: str
    term: str
    importance: int = 2
    explanation: str | None = None


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str


class Question(BaseModel):
    id: str
    text: str
    created_at: float


class Expansion(BaseModel):
    term: str
    explanation: str


class SlidePage(BaseModel):
    number: int
    title: str
    text: str


class SlideMatch(BaseModel):
    concept: str
    slide_number: int
    title: str
    excerpt: str
    score: float


class CreateSessionBody(BaseModel):
    provider: str = "xai"
    model: str = ""
    language: str = "it"


class ConfigBody(BaseModel):
    provider: str | None = None
    model: str | None = None
    language: str | None = None
