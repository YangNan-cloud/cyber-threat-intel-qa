from __future__ import annotations

import re
from app.schemas import Attribution, Evidence

ACTOR_RE = re.compile(r"\b(?:APT|UNC|FIN|TA)\d{1,5}\b", re.I)


class AttributionAgent:
    """Conservative attribution: no actor conclusion without corroborated evidence."""
    def assess(self, question: str, evidence: list[Evidence]) -> Attribution:
        requested = ACTOR_RE.search(question)
        actor = requested.group(0).upper() if requested else None
        supporting = []
        for item in evidence:
            haystack = f"{item.text} {' '.join(item.graph_paths)}"
            if actor and actor.lower() in haystack.lower():
                supporting.append(item.id)
        has_graph = any(item.graph_paths for item in evidence)
        if actor and len(supporting) >= 2 and has_graph:
            return Attribution(verdict="supported", actor=actor,
                rationale="至少两条检索证据与图谱路径共同支持该归因；仍应结合时间线和样本分析复核。",
                supporting_evidence_ids=supporting)
        if actor:
            return Attribution(verdict="inconclusive", actor=actor,
                rationale="现有证据不足以作确定性归因：需要独立来源、时间线或可验证图谱关系交叉印证。",
                supporting_evidence_ids=supporting)
        return Attribution(verdict="not_applicable", rationale="问题未要求威胁组织归因。")
