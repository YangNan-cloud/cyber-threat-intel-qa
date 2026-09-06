"""Adapter for member 2's intentionally small POST /search contract."""
from __future__ import annotations

import os
from typing import Any
import httpx

from app.schemas import Evidence


class RetrievalAgent:
    def __init__(self, endpoint: str | None = None) -> None:
        self.endpoint = endpoint or os.getenv("RETRIEVAL_URL", "http://localhost:8001/search")

    async def search(self, query: str, top_k: int = 6) -> list[Evidence]:
        """Accept either {results: [...]} or a bare list from the retrieval service.

        Expected result fields: id, text/chunk, source, url, score, entities, graph_paths.
        Unknown fields are ignored, so the retrieval module can evolve independently.
        """
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.post(self.endpoint, json={"query": query, "top_k": top_k})
                response.raise_for_status()
                body: Any = response.json()
        except (httpx.HTTPError, ValueError):
            return []
        rows = body.get("results", body) if isinstance(body, dict) else body
        if not isinstance(rows, list):
            return []
        evidence: list[Evidence] = []
        for index, row in enumerate(rows[:top_k]):
            if not isinstance(row, dict):
                continue
            evidence.append(Evidence(
                id=str(row.get("id", f"result-{index + 1}")),
                text=str(row.get("text", row.get("chunk", ""))),
                source=str(row.get("source", "未知来源")),
                url=row.get("url"), score=float(row.get("score", 0.0)),
                entities=row.get("entities") or {}, graph_paths=row.get("graph_paths") or [],
            ))
        return evidence
