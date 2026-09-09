"""Single-question evaluation agent for gold-labeled eval-set questions."""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

import httpx


def tokens(text: str) -> list[str]:
    return re.findall(r"[\w.-]+|[\u4e00-\u9fff]", text.lower())


def f1(gold: str, pred: str) -> float:
    gold_tokens = Counter(tokens(gold))
    pred_tokens = Counter(tokens(pred))
    common = sum((gold_tokens & pred_tokens).values())
    if not gold_tokens or not pred_tokens:
        return float(gold_tokens == pred_tokens)
    precision = common / sum(pred_tokens.values())
    recall = common / sum(gold_tokens.values())
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[1] / "lan_shuyang_qa" / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class EvaluationAgent:
    def __init__(self, dataset_path: str | Path | None = None) -> None:
        _load_dotenv()
        base_dir = Path(__file__).resolve().parent
        self.dataset_path = Path(dataset_path) if dataset_path else base_dir / "eval_dataset.jsonl"
        self.samples = _read_jsonl(self.dataset_path)
        self.by_question = {
            str(sample.get("question", "")).strip(): sample
            for sample in self.samples
            if sample.get("question")
        }

    @staticmethod
    def _retrieved_ids(citations: list[Any]) -> list[str]:
        ids: list[str] = []
        for item in citations:
            value = _field(item, "id")
            if value is not None:
                ids.append(str(value))
        return ids

    @staticmethod
    def _recall_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int = 5) -> float:
        return float(bool(set(relevant_ids) & set(retrieved_ids[:k])))

    @staticmethod
    def _mrr(retrieved_ids: list[str], relevant_ids: list[str]) -> float:
        relevant = set(relevant_ids)
        rank = next((index + 1 for index, doc_id in enumerate(retrieved_ids) if doc_id in relevant), None)
        return 1 / rank if rank else 0.0

    async def _llm_judge(
        self,
        sample: dict[str, Any],
        answer: str,
        citations: list[Any],
        metrics: dict[str, Any],
        attribution: Any,
        refusal: bool,
        refusal_reason: str | None,
    ) -> dict[str, Any] | None:
        key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not key:
            return {
                "available": False,
                "comment": "",
                "reason": "未配置 DEEPSEEK_API_KEY，无法生成 LLM 评价。",
            }

        evidence = "\n".join(
            f"[{index + 1}] id={_field(item, 'id', '')} source={_field(item, 'source', '')} "
            f"text={str(_field(item, 'text', ''))[:500]}"
            for index, item in enumerate(citations[:5])
        )
        prompt = (
            "你是网络威胁情报问答系统的评测员。请基于标准答案、系统答案、检索证据和指标，"
            "用中文给出一段简洁自然语言评价。评价应说明答案是否语义正确、证据是否命中、"
            "是否存在拒答或归因问题。不要重新生成答案，不要使用未给出的信息。\n\n"
            f"问题：{sample.get('question')}\n"
            f"标准答案：{sample.get('gold_answer')}\n"
            f"系统答案：{answer}\n"
            f"标准文档ID：{sample.get('gold_doc_ids', [])}\n"
            f"系统指标：{json.dumps(metrics, ensure_ascii=False)}\n"
            f"归因结果：actor={_field(attribution, 'actor')} verdict={_field(attribution, 'verdict')}\n"
            f"拒答结果：refusal={refusal} reason={refusal_reason}\n"
            f"检索证据：\n{evidence}"
        )
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"{os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com').rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                        "temperature": 0.1,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                response.raise_for_status()
                comment = response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            return {
                "available": False,
                "comment": "",
                "reason": f"LLM 评价生成失败：{type(exc).__name__}",
            }
        return {"available": True, "comment": comment.strip(), "reason": None}

    async def evaluate(
        self,
        query: str,
        answer: str,
        citations: list[Any],
        attribution: Any,
        confidence: float,
        refusal: bool,
        refusal_reason: str | None = None,
    ) -> dict[str, Any]:
        sample = self.by_question.get(query.strip())
        if not sample:
            return {
                "matched": False,
                "reason": "当前问题不在评测集中，无法计算需要 gold 标注的指标。",
                "metrics": None,
                "llm_judge": None,
            }

        gold_answer = str(sample.get("gold_answer", ""))
        relevant_ids = [str(x) for x in sample.get("gold_doc_ids", [])]
        retrieved_ids = self._retrieved_ids(citations)
        pred_actor = _field(attribution, "actor")
        pred_verdict = _field(attribution, "verdict")
        gold_actor = sample.get("gold_actor")
        gold_verdict = sample.get("gold_verdict")

        actor_correct = None if gold_actor is None else pred_actor == gold_actor
        verdict_correct = None if gold_verdict is None else pred_verdict == gold_verdict
        metrics = {
            "em": float(tokens(gold_answer) == tokens(answer)),
            "f1": round(f1(gold_answer, answer), 4),
            "recall_at_5": self._recall_at_k(retrieved_ids, relevant_ids, 5),
            "mrr": round(self._mrr(retrieved_ids, relevant_ids), 4),
            "actor_correct": actor_correct,
            "verdict_correct": verdict_correct,
            "refusal_correct": refusal == sample.get("should_refuse"),
        }
        llm_judge = await self._llm_judge(
            sample=sample,
            answer=answer,
            citations=citations,
            metrics=metrics,
            attribution=attribution,
            refusal=refusal,
            refusal_reason=refusal_reason,
        )

        return {
            "matched": True,
            "sample_id": sample.get("id"),
            "category": sample.get("category"),
            "matched_question": sample.get("question"),
            "gold_answer": gold_answer,
            "gold_doc_ids": relevant_ids,
            "gold_actor": gold_actor,
            "gold_verdict": gold_verdict,
            "should_refuse": sample.get("should_refuse"),
            "is_answerable": sample.get("is_answerable"),
            "prediction": answer,
            "retrieved_ids": retrieved_ids,
            "confidence": confidence,
            "refusal": refusal,
            "refusal_reason": refusal_reason,
            "metrics": metrics,
            "llm_judge": llm_judge,
        }
