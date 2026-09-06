# chunker.py

import re
import json
def split_text_chunk(text:str, chunk_size=512, overlap=100):
    """滑动窗口文本分块，用于向量化入库"""
    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = text[start:end]
        chunks.append(chunk.strip())
        start += (chunk_size - overlap)
    return chunks

# chunker.py build_chunk_metadata函数修改
def build_chunk_metadata(source_item:dict, chunk_text:str):
    """每一块附带元数据：来源文档、实体列表，后续检索返回给上层引用来源"""
    meta = {
        "source_id": source_item.get("id", ""),
        "source_text": chunk_text,
        # 真实数据集APT组织类型为 ThreatActor
        "apt_entities": json.dumps([e for e in source_item.get("entities",[]) if e["type"]=="ThreatActor"], ensure_ascii=False),
        # CVE漏洞类型 Vulnerability
        "cve_entities": json.dumps([e for e in source_item.get("entities",[]) if e["type"]=="Vulnerability"], ensure_ascii=False),
        "ioc_entities": json.dumps([], ensure_ascii=False), # 当前数据集缺少IOC，预留字段
    }
    return meta

if __name__ == "__main__":
    test_text = "这里是模拟威胁情报长文本......"*20
    res = split_text_chunk(test_text)
    print(len(res), res[0][0:100])