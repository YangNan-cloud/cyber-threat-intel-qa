from __future__ import annotations

import re, uuid
from collections import defaultdict
from pathlib import Path
import sys
from app.agents.retrieval import RetrievalAgent
from app.agents.attribution import AttributionAgent
from app.agents.safety import SafetyAgent
from app.agents.answer import AnswerAgent
from app.schemas import ChatResponse, SearchRequest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from unified_eval.evaluation_agent import EvaluationAgent

ENTITY_PATTERNS = {
    "cves": r"\bCVE-\d{4}-\d{4,7}\b", "ips": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "hashes": r"\b[a-fA-F0-9]{32,64}\b", "domains": r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b",
    "actors": r"\b(?:APT|UNC|FIN|TA)\d{1,5}\b",
}


class ThreatQAOrchestrator:
    def __init__(self) -> None:
        self.retrieval, self.attribution = RetrievalAgent(), AttributionAgent()
        self.safety, self.answer = SafetyAgent(), AnswerAgent()
        self.evaluation = EvaluationAgent()

    @staticmethod
    def _agent_query(request: SearchRequest) -> str:
        query = request.query.strip()
        file_content = getattr(request, "file_content", None) or getattr(request, "context", None)
        if isinstance(file_content, str):
            file_content = file_content.strip()
        if file_content and "[上传文件内容]" not in query:
            query = f"{query}\n\n[上传文件内容]\n{str(file_content)[:200000000]}"
        return query

    async def chat(self, request: SearchRequest) -> ChatResponse:
        agent_query = self._agent_query(request)
        evidence = await self.retrieval.search(agent_query, request.top_k)
        attribution = self.attribution.assess(agent_query, evidence)
        confidence, refusal, reason = self.safety.evaluate(evidence, attribution)
        answer = await self.answer.generate(agent_query, evidence, attribution, refusal)
        eval_query = agent_query.split("[上传文件内容]")[0].strip()
        evaluation = await self.evaluation.evaluate(
            query=eval_query,
            answer=answer,
            citations=evidence,
            attribution=attribution,
            confidence=confidence,
            refusal=refusal,
            refusal_reason=reason,
        )
        entities: dict[str, list[str]] = defaultdict(list)
        for item in evidence:
            for kind, values in item.entities.items(): entities[kind].extend(values)
            for kind, pattern in ENTITY_PATTERNS.items(): entities[kind].extend(re.findall(pattern, item.text, re.I))
        clean_entities = {k: sorted(set(v)) for k, v in entities.items()}
        return ChatResponse(answer=answer, citations=evidence, entities=clean_entities, attribution=attribution,
            confidence=confidence, refusal=refusal, refusal_reason=reason,
            conversation_id=request.conversation_id or str(uuid.uuid4()), evaluation=evaluation)
