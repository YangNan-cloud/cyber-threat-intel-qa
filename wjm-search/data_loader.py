# data_loader.py
import json
import os
from config import CTI_ANNOTATED_JSONL

def load_cti_jsonl(file_path=CTI_ANNOTATED_JSONL):
    """
    读取李佳颖输出 annotated_dataset.jsonl（CTI真实标注数据集）
    将原始数据中 relations head/tail由实体id(e1/e2)转换为实体name，兼容现有图谱构建逻辑
    返回列表，每条记录字段：id,text,entities,relations，relations中head/tail为实体name
    """
    if not os.path.exists(file_path):
        return []
    records = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            # 构建实体id -> {name, type}映射
            id2entity = {}
            for e in rec.get("entities", []):
                eid = e["id"]
                id2entity[eid] = {
                    "name": e["name"],
                    "type": e["type"]
                }
            # 转换关系：head/tail从e1/e2转为实体name
            new_rels = []
            for r in rec.get("relations", []):
                hid = r["head"]
                tid = r["tail"]
                if hid not in id2entity or tid not in id2entity:
                    continue
                h_name = id2entity[hid]["name"]
                t_name = id2entity[tid]["name"]
                new_rels.append({
                    "head": h_name,
                    "relation": r["type"],
                    "tail": t_name
                })
            # 改写entities，保留type、name，去掉id/spans/attrs，兼容原有extract_entities_relations
            simple_entities = []
            for e in rec.get("entities", []):
                simple_entities.append({
                    "type": e["type"],
                    "name": e["name"]
                })
            records.append({
                "id": str(rec.get("id")),
                "text": rec.get("text", ""),
                "entities": simple_entities,
                "relations": new_rels
            })
    return records


def extract_entities_relations(raw_data):
    """
    从结构化数据抽取实体与关系，用于构建知识图谱
    raw_data字段示例:
    {
        "text":"原始威胁情报文本",
        "entities":[{"type":"ThreatActor","name":"APT29"}],
        "relations":[{"head":"APT29","relation":"uses","tail":"Emotet"}]
    }
    """
    entity_list = []
    rel_list = []
    for item in raw_data:
        for e in item.get("entities", []):
            entity_list.append({"etype": e["type"], "ename": e["name"]})
        for r in item.get("relations", []):
            rel_list.append({"head": r["head"], "rel": r["relation"], "tail": r["tail"]})
    return entity_list, rel_list


if __name__ == "__main__":
    d = load_cti_jsonl()
    ents, rels = extract_entities_relations(d)
    print(f"读取CTI数据集，实体数量:{len(ents)} 关系数量:{len(rels)}")