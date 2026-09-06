"""Offline EM/F1 and confidence calibration evaluator.

Input JSONL fields: question, gold_answer, prediction, confidence.
"""
from __future__ import annotations
import argparse, json, re
from collections import Counter

def tokens(text: str) -> list[str]: return re.findall(r"[\w.-]+|[\u4e00-\u9fff]", text.lower())
def f1(gold: str, pred: str) -> float:
    g, p = Counter(tokens(gold)), Counter(tokens(pred)); common = sum((g & p).values())
    if not g or not p: return float(g == p)
    precision, recall = common / sum(p.values()), common / sum(g.values())
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0
def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("file"); args = parser.parse_args()
    rows = [json.loads(line) for line in open(args.file, encoding="utf-8") if line.strip()]
    scores = [f1(x["gold_answer"], x["prediction"]) for x in rows]
    em = sum(tokens(x["gold_answer"]) == tokens(x["prediction"]) for x in rows) / len(rows)
    brier = sum((float(x.get("confidence", 0)) - int(s >= .5)) ** 2 for x, s in zip(rows, scores)) / len(rows)
    print(json.dumps({"count":len(rows),"EM":round(em,4),"F1":round(sum(scores)/len(scores),4),"confidence_brier":round(brier,4)}, ensure_ascii=False))
if __name__ == "__main__": main()
