# evaluate_retrieval.py
"""
检索评测指标：Recall@K，MRR
输入：标准测试集，每一条包含 question、ground_truth_doc_id（标准答案对应的文档id）
"""
import json
import numpy as np
from hybrid_retriever import HybridRetriever

def calc_recall_at_k(retrieved_ids:list, ground_truth_ids:list, k:int):
    topk = retrieved_ids[:k]
    hit = any([g in topk for g in ground_truth_ids])
    return 1.0 if hit else 0.0

def calc_mrr(retrieved_ids:list, ground_truth_ids:list):
    for idx,docid in enumerate(retrieved_ids):
        if docid in ground_truth_ids:
            return 1.0/(idx+1)
    return 0.0

def evaluate(test_set_path:str):
    with open(test_set_path,"r",encoding="utf‑8") as f:
        test_samples = json.load(f)
    ret = HybridRetriever()
    recall_5_list = []
    recall_10_list = []
    mrr_list = []

    for sample in test_samples:
        q = sample["question"]
        gt_doc_ids = sample["ground_truth_doc_ids"]
        res = ret.retrieve(q)
        pred_ids = [c["metadata"]["source_id"] for c in res["candidates"]]

        recall_5_list.append(calc_recall_at_k(pred_ids, gt_doc_ids, k=5))
        recall_10_list.append(calc_recall_at_k(pred_ids, gt_doc_ids, k=10))
        mrr_list.append(calc_mrr(pred_ids, gt_doc_ids))

    report = {
        "Recall@5": float(np.mean(recall_5_list)),
        "Recall@10": float(np.mean(recall_10_list)),
        "MRR": float(np.mean(mrr_list)),
        "sample_count": len(test_samples)
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return report

if __name__ == "__main__":
    # 测试集来自李佳颖产出标准问答对
    evaluate("../dataset/test_retrieval_gt.json")