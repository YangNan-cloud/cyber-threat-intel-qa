#!/usr/bin/env python3
"""
DeepSeek LLM 补全标注(规则引擎的补充, 可选)

针对 MITRE 记录的描述文本, 调用 DeepSeek 补齐规则引擎无法覆盖的两类内容:
  - 无 MITRE ID 的软件(Software), 如 Hades、Cobalt Strike
  - 技术/手法(Technique / TTP), 如 double extortion、credential dumping

关系映射(与 annotate.py 现有 schema 对齐):
  - uses_software  -> 复用现有关系 uses   (ThreatActor -> Software)
  - uses_technique -> 新增关系 uses_technique (ThreatActor -> Technique / Software -> Technique)

设计要点:
  - 只补规则抽不到的无 ID 软件与 TTP; 不重复抽取已带 [Name](URL) 链接的实体。
  - 宁缺毋滥: 实体名必须能逐字定位到原文, 否则丢弃(防幻觉)。
  - 结果缓存到 dataset/llm_cache.json, 避免反复调用计费。

启用方式(annotate.py 会自动判断): 环境变量 LLM_ENRICH=1 或命令行传 --llm,
且 DEEPSEEK_API_KEY 非空。
"""
from __future__ import annotations

import hashlib
import json
import os
import re

from annotate import find_all_spans  # 复用容错连字符/空白的 span 定位


# ----------------------------------------------------------------------------
# Prompt
# ----------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "你是一名网络威胁情报(CTI)分析师与知识图谱工程师。给定一段 MITRE ATT&CK 组织/技术描述文本,"
    "请补齐规则引擎遗漏的实体与关系。\n\n"
    "规则引擎已经抽取了所有带 [名称](https://attack.mitre.org/...) 链接的组织(ThreatActor)与软件(Software),"
    "你只负责补充以下两类规则无法覆盖的内容:\n"
    "1. Software(软件): 文本中明确提及、但**没有** MITRE 链接的恶意软件/勒索软件/工具"
    "(例如 Hades、Cobalt Strike、custom RAT、point-of-sale malware)。**不要**重复抽取已带链接的软件。\n"
    "2. Technique(技术/手法): 攻击者使用的具体 TTP 短语"
    "(例如 spearphishing、lateral movement、double extortion、credential dumping、zero-day exploitation)。\n\n"
    "抽取约束:\n"
    "- 宁缺毋滥, 忠于原文: 只抽取明确提及或可直接推断的实体与关系, 严禁捏造或过度联想。\n"
    "- 实体 name 必须能逐字定位到原文(或其规范形式), 否则不要输出。\n"
    "- 若原文为 [Name](URL) 格式, 只取 Name, 不要带 URL。\n"
    "- 关系端点(name)必须都能在实体列表或原文组织名中找到。\n\n"
    "输出格式(严格合法 JSON, 不要输出任何额外说明):\n"
    '{"entities": [{"name": "实体名称", "type": "Software|Technique"}], '
    '"relations": [{"head": "头实体名称", "type": "uses_software|uses_technique", "tail": "尾实体名称"}]}\n'
    "关系类型说明:\n"
    "- uses_software: ThreatActor 使用某 Software(无 ID 软件)\n"
    "- uses_technique: ThreatActor 或 Software 使用某 Technique"
)

FEWSHOT = [
    {
        "role": "user",
        "content": (
            "Entity/Technique Name: Indrik Spider. Description: [Indrik Spider](https://attack.mitre.org/groups/G0119) "
            "initially started with the [Dridex](https://attack.mitre.org/software/S0384) banking Trojan, "
            "and by 2017 began ransomware operations using [BitPaymer](https://attack.mitre.org/software/S0570), "
            "[WastedLocker](https://attack.mitre.org/software/S0612), and Hades ransomware."
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps(
            {
                "entities": [
                    {"name": "Hades", "type": "Software"},
                    {"name": "ransomware operations", "type": "Technique"},
                ],
                "relations": [
                    {"head": "Indrik Spider", "type": "uses_software", "tail": "Hades"},
                    {"head": "Indrik Spider", "type": "uses_technique", "tail": "ransomware operations"},
                ],
            },
            ensure_ascii=False,
        ),
    },
]


# ----------------------------------------------------------------------------
# 工具
# ----------------------------------------------------------------------------

def _strip_markdown(name: str) -> str:
    """[Name](URL) -> Name; 压缩空白."""
    name = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", name)
    return re.sub(r"\s+", " ", name).strip()


def _load_cache(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(path: str, cache: dict) -> None:
    try:
        json.dump(cache, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception:
        pass


def call_deepseek(text: str, cache_path: str = "llm_cache.json"):
    """调用 DeepSeek 补全标注, 带本地缓存. 失败/未配置时返回 None."""
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        print("[LLM] 跳过: 未设置 DEEPSEEK_API_KEY")
        return None

    cache = _load_cache(cache_path)
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if h in cache:
        return cache[h]

    try:
        import requests
    except ImportError:
        print("[LLM] 跳过: 缺少 requests 依赖 (pip install requests)")
        return None

    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + FEWSHOT + [
        {"role": "user", "content": f"请分析以下威胁情报文本:\n{text}"}
    ]
    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0.1,
                "messages": messages,
                "response_format": {"type": "json_object"},
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = json.loads(resp.json()["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"[LLM Error] {e}")
        return None

    cache[h] = data
    _save_cache(cache_path, cache)
    return data


# ----------------------------------------------------------------------------
# 应用补全结果
# ----------------------------------------------------------------------------

_REL_MAP = {"uses_software": "uses", "uses_technique": "uses_technique"}


def _resolve(name_to_ent: dict, name, actor):
    """按名字解析关系端点 -> 实体; 找不到时若与主组织名近似则回退到 actor."""
    if not isinstance(name, str):
        return None
    key = _strip_markdown(name).lower()
    if key in name_to_ent:
        return name_to_ent[key]
    if actor is not None:
        aname = actor["name"].lower()
        if aname and (aname in key or key in aname):
            return actor
    return None


def enrich_mitre(annotator, actor) -> int:
    """对 annotate_mitre 的产物做 LLM 补全, 就地修改 annotator.entities / relations.

    返回新增实体数(0 表示未启用/无结果).
    """
    text = annotator.text
    if not text or not actor:
        return 0

    data = call_deepseek(text)
    if not isinstance(data, dict):
        return 0

    # 已有实体(小写名 -> 实体) 与已消费 span, 用于去重
    name_to_ent = {e["name"].lower(): e for e in annotator.entities}
    existing_spans = {s for e in annotator.entities for s in e["spans"]}

    added = 0
    for ent in data.get("entities", []):
        if not isinstance(ent, dict):
            continue
        name = _strip_markdown(str(ent.get("name", "")))
        etype = str(ent.get("type", "")).strip()
        if not name or etype not in ("Software", "Technique"):
            continue
        key = name.lower()
        if key in name_to_ent:
            continue  # 重复实体
        spans = [s for s in find_all_spans(text, name, re.I) if s not in existing_spans]
        if not spans:
            continue  # 防幻觉: 名字无法逐字定位到原文
        new_ent = annotator.add_entity(etype, name, attrs={"source": "LLM"}, spans=spans)
        name_to_ent[key] = new_ent
        existing_spans.update(spans)
        added += 1

    for rel in data.get("relations", []):
        if not isinstance(rel, dict):
            continue
        rtype = _REL_MAP.get(rel.get("type"))
        if not rtype:
            continue
        head = _resolve(name_to_ent, rel.get("head"), actor)
        tail = _resolve(name_to_ent, rel.get("tail"), None)
        if head is None or tail is None or head is tail:
            continue
        # 跳过与现有边完全相同的重复边(如规则已抽出 actor->Dridex 的 uses)
        if any(r["head"] == head["id"] and r["type"] == rtype and r["tail"] == tail["id"]
               for r in annotator.relations):
            continue
        annotator.add_relation(head, rtype, tail, method="llm_inference")

    return added
