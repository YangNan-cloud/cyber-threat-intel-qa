"""Run the unified offline evaluation dataset against the QA API.

This script writes:
- evaluation_predictions.jsonl
- evaluation_summary.json
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from evaluate_qa import f1, tokens


DEFAULT_CHAT_URL = "http://127.0.0.1:8000/api/chat"
DEFAULT_RETRIEVAL_URL = "http://127.0.0.1:8001/api/retrieval"
DEFAULT_TOP_K = 6


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} is not valid JSON: {exc}") from exc
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read().decode("utf-8")
    parsed = json.loads(data)
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object from {url}, got {type(parsed).__name__}")
    return parsed


def api_error(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        detail = exc.read().decode("utf-8", errors="replace")
        return f"HTTP {exc.code}: {detail}"
    if isinstance(exc, urllib.error.URLError):
        return f"Connection error: {exc.reason}"
    if isinstance(exc, TimeoutError):
        return "Request timed out"
    return f"{type(exc).__name__}: {exc}"


def citation_ids(chat_body: dict[str, Any]) -> list[str] | None:
    citations = chat_body.get("citations")
    if not isinstance(citations, list):
        return None
    ids: list[str] = []
    for item in citations:
        if isinstance(item, dict) and "id" in item:
            ids.append(str(item["id"]))
    return ids


def retrieval_ids(retrieval_body: dict[str, Any]) -> list[str]:
    rows = retrieval_body.get("results", retrieval_body.get("citations", []))
    if not isinstance(rows, list):
        return []
    ids: list[str] = []
    for item in rows:
        if isinstance(item, dict) and "id" in item:
            ids.append(str(item["id"]))
    return ids


def build_prediction(
    sample: dict[str, Any],
    chat_url: str,
    retrieval_url: str,
    top_k: int,
    timeout: float,
) -> tuple[dict[str, Any], bool]:
    row = dict(sample)
    row["relevant_ids"] = list(sample.get("gold_doc_ids") or [])
    row.update(
        {
            "prediction": "",
            "retrieved_ids": [],
            "confidence": 0.0,
            "refusal": None,
            "refusal_reason": None,
            "pred_actor": None,
            "pred_verdict": None,
        }
    )
    try:
        chat_body = post_json(chat_url, {"query": sample["question"], "top_k": top_k}, timeout)
        attribution = chat_body.get("attribution") or {}
        if not isinstance(attribution, dict):
            attribution = {}
        row.update(
            {
                "prediction": str(chat_body.get("answer", "")),
                "confidence": float(chat_body.get("confidence", 0.0) or 0.0),
                "refusal": chat_body.get("refusal"),
                "refusal_reason": chat_body.get("refusal_reason"),
                "pred_actor": attribution.get("actor"),
                "pred_verdict": attribution.get("verdict"),
                "citations": chat_body.get("citations", []),
                "conversation_id": chat_body.get("conversation_id"),
            }
        )
        ids = citation_ids(chat_body)
        if ids is None:
            retrieval_body = post_json(
                retrieval_url, {"query": sample["question"], "top_k": top_k}, timeout
            )
            ids = retrieval_ids(retrieval_body)
        row["retrieved_ids"] = ids
        return row, True
    except Exception as exc:
        row["error"] = api_error(exc)
        return row, False


def safe_average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def exact_match(row: dict[str, Any]) -> bool:
    return tokens(row.get("gold_answer", "")) == tokens(row.get("prediction", ""))


def row_f1(row: dict[str, Any]) -> float:
    return f1(row.get("gold_answer", ""), row.get("prediction", ""))


def retrieval_hit(row: dict[str, Any], k: int = 5) -> bool:
    relevant = set(str(x) for x in row.get("relevant_ids", row.get("gold_doc_ids", [])))
    retrieved = [str(x) for x in row.get("retrieved_ids", [])]
    return bool(relevant & set(retrieved[:k]))


def reciprocal_rank(row: dict[str, Any]) -> float:
    relevant = set(str(x) for x in row.get("relevant_ids", row.get("gold_doc_ids", [])))
    retrieved = [str(x) for x in row.get("retrieved_ids", [])]
    rank = next((index + 1 for index, doc_id in enumerate(retrieved) if doc_id in relevant), None)
    return 1 / rank if rank else 0.0


def basic_metrics(rows: list[dict[str, Any]], include_retrieval: bool = True) -> dict[str, Any]:
    metrics: dict[str, Any] = {"count": len(rows)}
    if not rows:
        metrics.update({"EM": 0.0, "F1": 0.0})
        if include_retrieval:
            metrics.update({"Recall@5_any_hit": 0.0, "MRR": 0.0})
        return metrics
    metrics["EM"] = round(safe_average([float(exact_match(row)) for row in rows]), 4)
    metrics["F1"] = round(safe_average([row_f1(row) for row in rows]), 4)
    if include_retrieval:
        metrics["Recall@5_any_hit"] = round(
            safe_average([float(retrieval_hit(row, 5)) for row in rows]), 4
        )
        metrics["MRR"] = round(safe_average([reciprocal_rank(row) for row in rows]), 4)
    return metrics


def metrics_with_confidence(rows: list[dict[str, Any]], include_retrieval: bool = True) -> dict[str, Any]:
    metrics = basic_metrics(rows, include_retrieval=include_retrieval)
    if rows:
        metrics["average_confidence"] = round(
            safe_average([float(row.get("confidence", 0.0) or 0.0) for row in rows]), 4
        )
        metrics["refusal_rate"] = round(safe_average([float(row.get("refusal") is True) for row in rows]), 4)
    else:
        metrics["average_confidence"] = 0.0
        metrics["refusal_rate"] = 0.0
    return metrics


def compute_attribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    attr_rows = [row for row in rows if row.get("category") == "attribution"]
    errors = []
    verdict_distribution: dict[str, int] = {"supported": 0, "inconclusive": 0, "not_applicable": 0}
    for row in attr_rows:
        pred_verdict = row.get("pred_verdict")
        if pred_verdict in verdict_distribution:
            verdict_distribution[pred_verdict] += 1
        else:
            verdict_distribution[str(pred_verdict)] = verdict_distribution.get(str(pred_verdict), 0) + 1
        actor_ok = row.get("gold_actor") == row.get("pred_actor")
        verdict_ok = row.get("gold_verdict") == pred_verdict
        if not (actor_ok and verdict_ok):
            errors.append(
                {
                    "id": row.get("id"),
                    "question": row.get("question"),
                    "gold_actor": row.get("gold_actor"),
                    "pred_actor": row.get("pred_actor"),
                    "gold_verdict": row.get("gold_verdict"),
                    "pred_verdict": pred_verdict,
                }
            )
    count = len(attr_rows)
    return {
        "attribution_count": count,
        "actor_accuracy": round(
            safe_average([float(row.get("gold_actor") == row.get("pred_actor")) for row in attr_rows]), 4
        ),
        "verdict_accuracy": round(
            safe_average([float(row.get("gold_verdict") == row.get("pred_verdict")) for row in attr_rows]), 4
        ),
        "both_correct_accuracy": round(
            safe_average(
                [
                    float(
                        row.get("gold_actor") == row.get("pred_actor")
                        and row.get("gold_verdict") == row.get("pred_verdict")
                    )
                    for row in attr_rows
                ]
            ),
            4,
        ),
        "pred_verdict_distribution": verdict_distribution,
        "errors": errors,
    }


def compute_refusal(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    should_refuse = [row for row in rows if row.get("should_refuse") is True]
    should_answer = [row for row in rows if row.get("should_refuse") is not True]
    correct_refusal = [row for row in should_refuse if row.get("refusal") is True]
    missed_refusal = [row for row in should_refuse if row.get("refusal") is not True]
    false_refusal = [row for row in should_answer if row.get("refusal") is True]
    normal_answer = [row for row in should_answer if row.get("refusal") is not True]
    correct = len(correct_refusal) + len(normal_answer)
    return {
        "total": total,
        "should_refuse_count": len(should_refuse),
        "should_answer_count": len(should_answer),
        "correct_refusal_count": len(correct_refusal),
        "missed_refusal_count": len(missed_refusal),
        "false_refusal_count": len(false_refusal),
        "normal_answer_count": len(normal_answer),
        "refusal_accuracy": round(correct / total, 4) if total else 0.0,
        "false_refusal_rate": round(len(false_refusal) / len(should_answer), 4) if should_answer else 0.0,
        "answer_coverage": round(len(normal_answer) / len(should_answer), 4) if should_answer else 0.0,
    }


def compute_error_analysis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[str]] = {
        "retrieval_miss": [],
        "false_refusal": [],
        "missed_refusal": [],
        "attribution_error": [],
        "answered_but_low_f1": [],
    }
    for row in rows:
        row_id = str(row.get("id"))
        relevant = row.get("relevant_ids", row.get("gold_doc_ids", []))
        if relevant and not retrieval_hit(row, 5):
            buckets["retrieval_miss"].append(row_id)
        if row.get("should_refuse") is not True and row.get("refusal") is True:
            buckets["false_refusal"].append(row_id)
        if row.get("should_refuse") is True and row.get("refusal") is not True:
            buckets["missed_refusal"].append(row_id)
        if row.get("category") == "attribution" and (
            row.get("gold_actor") != row.get("pred_actor")
            or row.get("gold_verdict") != row.get("pred_verdict")
        ):
            buckets["attribution_error"].append(row_id)
        if (
            row.get("should_refuse") is not True
            and row.get("refusal") is not True
            and row_f1(row) < 0.5
        ):
            buckets["answered_but_low_f1"].append(row_id)
    return {name: {"count": len(ids), "ids": ids} for name, ids in buckets.items()}


def compute_f1_diagnosis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [row for row in rows if row.get("is_answerable") is True]
    refused = [row for row in rows if row.get("refusal") is True]
    false_refused_answerable = [
        row for row in answerable if row.get("should_refuse") is not True and row.get("refusal") is True
    ]
    answered_answerable = [
        row for row in answerable if row.get("should_refuse") is not True and row.get("refusal") is not True
    ]
    retrieval_hit_answerable = [row for row in answerable if retrieval_hit(row, 5)]
    return {
        "total_refused_count": len(refused),
        "answerable_should_answer_count": len(
            [row for row in answerable if row.get("should_refuse") is not True]
        ),
        "answerable_false_refusal_count": len(false_refused_answerable),
        "answered_answerable_metrics": basic_metrics(answered_answerable, include_retrieval=True),
        "retrieval_hit_answerable_metrics": basic_metrics(retrieval_hit_answerable, include_retrieval=True),
    }


def confidence_bucket(confidence: float) -> str:
    buckets = [
        (0.0, 0.3, "0.0-0.3"),
        (0.3, 0.4, "0.3-0.4"),
        (0.4, 0.5, "0.4-0.5"),
        (0.5, 0.55, "0.5-0.55"),
        (0.55, 0.6, "0.55-0.6"),
        (0.6, 0.7, "0.6-0.7"),
        (0.7, 1.0000001, "0.7-1.0"),
    ]
    for lower, upper, label in buckets:
        if lower <= confidence < upper:
            return label
    return "out_of_range"


def confidence_bucket_metrics(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    labels = ["0.0-0.3", "0.3-0.4", "0.4-0.5", "0.5-0.55", "0.55-0.6", "0.6-0.7", "0.7-1.0"]
    grouped: dict[str, list[dict[str, Any]]] = {label: [] for label in labels}
    for row in rows:
        grouped.setdefault(confidence_bucket(float(row.get("confidence", 0.0) or 0.0)), []).append(row)

    result: dict[str, dict[str, Any]] = {}
    for label in labels:
        bucket_rows = grouped[label]
        should_answer = [row for row in bucket_rows if row.get("should_refuse") is not True]
        should_refuse = [row for row in bucket_rows if row.get("should_refuse") is True]
        result[label] = {
            "count": len(bucket_rows),
            "should_answer_count": len(should_answer),
            "should_refuse_count": len(should_refuse),
            "refusal_rate": round(
                safe_average([float(row.get("refusal") is True) for row in bucket_rows]), 4
            ),
            "average_F1": round(safe_average([row_f1(row) for row in bucket_rows]), 4),
            "retrieval_hit_rate": round(
                safe_average([float(retrieval_hit(row, 5)) for row in bucket_rows]), 4
            ),
            "normal_answer_count": len(
                [row for row in should_answer if row.get("refusal") is not True]
            ),
            "false_refusal_count": len(
                [row for row in should_answer if row.get("refusal") is True]
            ),
            "missed_refusal_count": len(
                [row for row in should_refuse if row.get("refusal") is not True]
            ),
        }
    return result


def retrieval_quality_confidence(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    hit_rows = [row for row in rows if retrieval_hit(row, 5)]
    miss_rows = [row for row in rows if not retrieval_hit(row, 5)]

    def group_metrics(group: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "count": len(group),
            "average_confidence": round(
                safe_average([float(row.get("confidence", 0.0) or 0.0) for row in group]), 4
            ),
            "average_F1": round(safe_average([row_f1(row) for row in group]), 4),
            "refusal_rate": round(safe_average([float(row.get("refusal") is True) for row in group]), 4),
        }

    return {"retrieval_hit_true": group_metrics(hit_rows), "retrieval_hit_false": group_metrics(miss_rows)}


def f1_confidence_groups(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    answerable = [row for row in rows if row.get("is_answerable") is True]
    groups = {
        "F1=0": [row for row in answerable if row_f1(row) == 0],
        "0<F1<0.5": [row for row in answerable if 0 < row_f1(row) < 0.5],
        "F1>=0.5": [row for row in answerable if row_f1(row) >= 0.5],
    }
    return {
        label: {
            "count": len(group),
            "average_confidence": round(
                safe_average([float(row.get("confidence", 0.0) or 0.0) for row in group]), 4
            ),
        }
        for label, group in groups.items()
    }


def simulate_thresholds(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for threshold in (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65):
        should_refuse = [row for row in rows if row.get("should_refuse") is True]
        should_answer = [row for row in rows if row.get("should_refuse") is not True]

        def simulated_refusal(row: dict[str, Any]) -> bool:
            return float(row.get("confidence", 0.0) or 0.0) < threshold

        correct_refusal = [row for row in should_refuse if simulated_refusal(row)]
        missed_refusal = [row for row in should_refuse if not simulated_refusal(row)]
        false_refusal = [row for row in should_answer if simulated_refusal(row)]
        normal_answer = [row for row in should_answer if not simulated_refusal(row)]
        allowed_answerable = [
            row
            for row in rows
            if row.get("is_answerable") is True and row.get("should_refuse") is not True and not simulated_refusal(row)
        ]
        result[f"{threshold:.2f}"] = {
            "correct_refusal_count": len(correct_refusal),
            "false_refusal_count": len(false_refusal),
            "missed_refusal_count": len(missed_refusal),
            "normal_answer_count": len(normal_answer),
            "refusal_accuracy": round((len(correct_refusal) + len(normal_answer)) / len(rows), 4)
            if rows
            else 0.0,
            "false_refusal_rate": round(len(false_refusal) / len(should_answer), 4)
            if should_answer
            else 0.0,
            "answer_coverage": round(len(normal_answer) / len(should_answer), 4)
            if should_answer
            else 0.0,
            "allowed_answerable": {
                "count": len(allowed_answerable),
                "average_F1": round(safe_average([row_f1(row) for row in allowed_answerable]), 4),
                "retrieval_hit_rate": round(
                    safe_average([float(retrieval_hit(row, 5)) for row in allowed_answerable]), 4
                ),
            },
        }
    return result


def compute_confidence_analysis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "threshold_used_by_current_predictions": 0.55,
        "buckets": confidence_bucket_metrics(rows),
        "retrieval_quality": retrieval_quality_confidence(rows),
        "answerable_f1_groups": f1_confidence_groups(rows),
        "threshold_simulation": simulate_thresholds(rows),
        "formula_notes": {
            "source_file": "lan_shuyang_qa/app/agents/safety.py",
            "formula": "confidence = clamp(0.55 * average_retrieval_score + source_bonus + graph_bonus - attribution_penalty, 0, 1), rounded to 2 decimals",
            "average_retrieval_score_weight": 0.55,
            "source_bonus": "min(0.18, 0.06 * unique_source_count)",
            "graph_bonus": "0.10 if any evidence has graph_paths else 0.0",
            "attribution_penalty": "0.18 if attribution.verdict == inconclusive else 0.0",
            "has_generation_confidence": False,
            "contains_answer_quality_signal": False,
        },
    }


def compute_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_category = {
        category: metrics_with_confidence(
            [row for row in rows if row.get("category") == category], include_retrieval=True
        )
        for category in ("CVE", "APT", "attribution", "unknown/refusal")
    }
    answerable_rows = [row for row in rows if row.get("is_answerable") is True]
    unanswerable_rows = [row for row in rows if row.get("is_answerable") is False]
    return {
        "overall": basic_metrics(rows, include_retrieval=True),
        "by_category": by_category,
        "answerability": {
            "is_answerable_true": metrics_with_confidence(answerable_rows, include_retrieval=True),
            "is_answerable_false": {
                "count": len(unanswerable_rows),
                "refusal_rate": round(
                    safe_average([float(row.get("refusal") is True) for row in unanswerable_rows]), 4
                ),
                "average_confidence": round(
                    safe_average([float(row.get("confidence", 0.0) or 0.0) for row in unanswerable_rows]), 4
                ),
            },
        },
        "attribution": compute_attribution(rows),
        "refusal": compute_refusal(rows),
        "confidence": {
            "average_confidence": round(
                safe_average([float(row.get("confidence", 0.0) or 0.0) for row in rows]), 4
            )
        },
        "confidence_analysis": compute_confidence_analysis(rows),
        "error_analysis": compute_error_analysis(rows),
        "f1_diagnosis": compute_f1_diagnosis(rows),
        "ioc_evaluation": {
            "available": False,
            "reason": "IOC positive evaluation unavailable because current dataset has no structured IOC positive samples.",
        },
    }


def main() -> int:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=base_dir / "eval_dataset.jsonl")
    parser.add_argument("--predictions", type=Path, default=base_dir / "evaluation_predictions.jsonl")
    parser.add_argument("--summary", type=Path, default=base_dir / "evaluation_summary.json")
    parser.add_argument("--chat-url", default=DEFAULT_CHAT_URL)
    parser.add_argument("--retrieval-url", default=DEFAULT_RETRIEVAL_URL)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Recompute evaluation_summary.json from an existing predictions JSONL file.",
    )
    args = parser.parse_args()

    samples = read_jsonl(args.dataset)
    if args.summary_only:
        predictions = read_jsonl(args.predictions)
        summary = compute_summary(predictions)
        args.summary.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Loaded predictions: {len(predictions)}")
        print(f"Summary: {args.summary}")
        return 0

    predictions: list[dict[str, Any]] = []
    success = 0
    failure = 0
    first_error: str | None = None
    total = len(samples)

    for index, sample in enumerate(samples, 1):
        print(f"[{index}/{total}] {sample.get('id', '<missing-id>')}", flush=True)
        row, ok = build_prediction(
            sample,
            chat_url=args.chat_url,
            retrieval_url=args.retrieval_url,
            top_k=args.top_k,
            timeout=args.timeout,
        )
        predictions.append(row)
        if ok:
            success += 1
        else:
            failure += 1
            first_error = first_error or row.get("error")

    write_jsonl(args.predictions, predictions)
    summary = compute_summary(predictions)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Success samples: {success}")
    print(f"Failed samples: {failure}")
    if success == 0 and first_error:
        print(f"QA API appears unavailable at {args.chat_url}: {first_error}", file=sys.stderr)
    print(f"Predictions: {args.predictions}")
    print(f"Summary: {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
