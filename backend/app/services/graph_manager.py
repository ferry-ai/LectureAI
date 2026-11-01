"""Incremental keyword graph. Nodes are never rebuilt from scratch."""

from __future__ import annotations

import re

from app.models import GraphEdge, GraphNode, KeywordIn
from app.textutil import collapse, norm_term

_SLUG = re.compile(r"[^a-z0-9à-ÿ]+")


class GraphManager:
    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.edges: dict[str, GraphEdge] = {}
        self._by_norm: dict[str, str] = {}

    def apply_keywords(self, keywords: list[KeywordIn]) -> tuple[list[GraphNode], list[GraphEdge]]:
        """Insert new terms, then link them. Unknown related_to targets are skipped."""
        added_nodes: list[GraphNode] = []
        for keyword in keywords:
            node, created = self._upsert(keyword.term, keyword.importance)
            if node is None:
                continue
            if created:
                added_nodes.append(node)

        added_edges: list[GraphEdge] = []
        for keyword in keywords:
            source = self._by_norm.get(norm_term(keyword.term))
            if source is None:
                continue
            for related in keyword.related_to:
                target = self._by_norm.get(norm_term(related))
                if target is None or target == source:
                    continue
                edge, created = self._link(source, target)
                if created:
                    added_edges.append(edge)
        return added_nodes, added_edges

    def set_explanation(self, term: str, explanation: str) -> GraphNode | None:
        text = collapse(explanation)[:800]
        if not text:
            return None
        node, _created = self._upsert(term, 2)
        if node is None:
            return None
        node.explanation = text
        return node

    def prompt_view(self, limit: int = 40) -> list[dict]:
        relations: dict[str, list[str]] = {node_id: [] for node_id in self.nodes}
        for edge in self.edges.values():
            relations[edge.source].append(self.nodes[edge.target].term)
            relations[edge.target].append(self.nodes[edge.source].term)
        ranked = sorted(self.nodes.values(), key=lambda node: (-node.importance, node.term.casefold()))
        return [
            {
                "term": node.term,
                "importance": node.importance,
                "related_to": relations[node.id][:8],
            }
            for node in ranked[:limit]
        ]

    def snapshot(self) -> dict:
        nodes = sorted(self.nodes.values(), key=lambda node: (-node.importance, node.term.casefold()))
        return {
            "nodes": [node.model_dump() for node in nodes],
            "edges": [edge.model_dump() for edge in self.edges.values()],
        }

    def _upsert(self, term: str, importance: int) -> tuple[GraphNode | None, bool]:
        label = collapse(term)[:80]
        if not label:
            return None, False
        key = norm_term(label)
        clamped = max(1, min(5, int(importance)))
        existing_id = self._by_norm.get(key)
        if existing_id is not None:
            node = self.nodes[existing_id]
            if clamped > node.importance:
                node.importance = clamped
            return node, False
        node = GraphNode(id=self._unique_id(key), term=label, importance=clamped)
        self.nodes[node.id] = node
        self._by_norm[key] = node.id
        return node, True

    def _link(self, source: str, target: str) -> tuple[GraphEdge, bool]:
        left, right = sorted((source, target))
        edge_id = f"{left}__{right}"
        existing = self.edges.get(edge_id)
        if existing is not None:
            return existing, False
        edge = GraphEdge(id=edge_id, source=left, target=right)
        self.edges[edge_id] = edge
        return edge, True

    def _unique_id(self, key: str) -> str:
        base = _SLUG.sub("-", key).strip("-")[:48] or "termine"
        candidate = base
        suffix = 2
        while candidate in self.nodes:
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate
