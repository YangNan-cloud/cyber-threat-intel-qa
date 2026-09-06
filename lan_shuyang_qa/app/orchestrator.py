from __future__ import annotations

import re, uuid
from collections import defaultdict
from app.agents.retrieval import RetrievalAgent
from app.agents.attribution import AttributionAgent
from app.agents.safety import SafetyAgent
from app.agents.answer import AnswerAgent
from app.schemas import ChatResponse, SearchRequest

ENTITY_PATTERNS = {
    "cves": r"\bCVE-\d{4}-\d{4,7}\b", "ips": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "hashes": r"\b[a-fA-F0-9]{32,64}\b", "domains": r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b",
    "actors": r"\b(?:APT|UNC|FIN|TA)\d{1,5}\b",
}


class ThreatQAOrchestrator:
    def __init__(self) -> None:
        self.retrieval, self.attribution = RetrievalAgent(), AttributionAgent()
        self.safety, self.answer = SafetyAgent(), AnswerAgent()

    async def chat(self, request: SearchRequest) -> ChatResponse:
        evidence = await self.retrieval.search(request.query, request.top_k)
        attribution = self.attribution.assess(request.query, evidence)
        confidence, refusal, reason = self.safety.evaluate(evidence, attribution)
        answer = await self.answer.generate(request.query, evidence, attribution, refusal)
        entities: dict[str, list[str]] = defaultdict(list)
        for item in evidence:
            for kind, values in item.entities.items(): entities[kind].extend(values)
            for kind, pattern in ENTITY_PATTERNS.items(): entities[kind].extend(re.findall(pattern, item.text, re.I))
        clean_entities = {k: sorted(set(v)) for k, v in entities.items()}
        return ChatResponse(answer=answer, citations=evidence, entities=clean_entities, attribution=attribution,
            confidence=confidence, refusal=refusal, refusal_reason=reason,
            conversation_id=request.conversation_id or str(uuid.uuid4()))
