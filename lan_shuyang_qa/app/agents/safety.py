from __future__ import annotations

import os
from app.schemas import Attribution, Evidence


class SafetyAgent:
    def __init__(self, threshold: float | None = None) -> None:
        self.threshold = threshold if threshold is not None else float(os.getenv("CONFIDENCE_THRESHOLD", "0.55"))

    def evaluate(self, evidence: list[Evidence], attribution: Attribution) -> tuple[float, bool, str | None]:
        if not evidence:
            return 0.0, True, "未检索到可引用的威胁情报，不能据此给出结论。"
        score = sum(max(0.0, min(1.0, item.score)) for item in evidence) / len(evidence)
        source_bonus = min(0.18, 0.06 * len({item.source for item in evidence}))
        graph_bonus = 0.10 if any(item.graph_paths for item in evidence) else 0.0
        attribution_penalty = 0.18 if attribution.verdict == "inconclusive" else 0.0
        confidence = round(max(0.0, min(1.0, 0.55 * score + source_bonus + graph_bonus - attribution_penalty)), 2)
        if confidence < self.threshold:
            return confidence, True, f"证据置信度 {confidence:.0%} 低于阈值 {self.threshold:.0%}；请补充 IOC、CVE 或时间范围。"
        return confidence, False, None
