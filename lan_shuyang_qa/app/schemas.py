from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=6, ge=1, le=20)
    conversation_id: str | None = None


class Evidence(BaseModel):
    id: str
    text: str
    source: str
    url: str | None = None
    score: float = 0.0
    entities: dict[str, list[str]] = Field(default_factory=dict)
    graph_paths: list[str] = Field(default_factory=list)


class Attribution(BaseModel):
    verdict: Literal["supported", "inconclusive", "not_applicable"]
    actor: str | None = None
    rationale: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    citations: list[Evidence]
    entities: dict[str, list[str]]
    attribution: Attribution
    confidence: float
    refusal: bool
    refusal_reason: str | None = None
    conversation_id: str
