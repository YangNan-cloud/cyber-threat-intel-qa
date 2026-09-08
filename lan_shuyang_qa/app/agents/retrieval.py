"""Adapter for member 2's intentionally small POST /search contract."""
from __future__ import annotations

import os
from typing import Any
import httpx

from app.schemas import Evidence


class RetrievalAgent:
    def __init__(self, endpoint: str | None = None) -> None:
        default = "http://localhost:8001/api/retrieval"
        env_endpoint = os.getenv("RETRIEVAL_URL")
        candidates = []
        if endpoint:
            candidates.append(endpoint.rstrip("/"))
        if env_endpoint:
            candidates.append(env_endpoint.rstrip("/"))
        candidates.extend([
            default,
            "http://localhost:8001/search",
        ])
        deduped = []
        for value in candidates:
            if value not in deduped:
                deduped.append(value)
        self.endpoints = deduped
        self.endpoint = self.endpoints[0]

    async def search(self, query: str, top_k: int = 6) -> list[Evidence]:
        """Accept either {results: [...]} or a bare list from the retrieval service.

        Expected result fields: id, text/chunk, source, url, score, entities, graph_paths.
        Unknown fields are ignored, so the retrieval module can evolve independently.
        """
        last_error: Exception | None = None
        for endpoint in self.endpoints:
            try:
                async with httpx.AsyncClient(timeout=8) as client:
                    response = await client.post(endpoint, json={"query": query, "top_k": top_k})
                    response.raise_for_status()
                    body: Any = response.json()
                break
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                continue
        else:
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
