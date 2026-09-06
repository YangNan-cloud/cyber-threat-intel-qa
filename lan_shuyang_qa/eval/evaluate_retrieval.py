"""Recall@K and MRR evaluator. JSONL rows: relevant_ids, retrieved_ids."""
from __future__ import annotations
import argparse, json
def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("file"); p.add_argument("--k",type=int,default=5); a=p.parse_args()
    rows=[json.loads(x) for x in open(a.file,encoding="utf-8") if x.strip()]; recall=[]; reciprocal=[]
    for row in rows:
        rel,got=set(row["relevant_ids"]),row["retrieved_ids"]; recall.append(bool(rel & set(got[:a.k])))
        rank=next((i+1 for i,x in enumerate(got) if x in rel),None); reciprocal.append(1/rank if rank else 0)
    print(json.dumps({f"Recall@{a.k}":round(sum(recall)/len(rows),4),"MRR":round(sum(reciprocal)/len(rows),4),"count":len(rows)}))
if __name__ == "__main__": main()
