import os
import json

import requests

dataset = []
print("开始自动收集威胁情报数据...")


def sample_iocs(data, target=70):
    """从 ThreatFox 数据中均衡抽样: 按 ioc_type 分层 + 恶意软件家族去重 + 置信度优先。

    避免 `data[:70]` 按时间序导致的家族/类型偏斜(如大量 IClickFix/ClearFake)。
    """
    quotas = {"domain": 24, "ip:port": 18, "url": 12, "hash": 16}
    buckets = {"domain": [], "ip:port": [], "url": [], "hash": []}
    for x in data:
        t = x.get("ioc_type")
        if t in ("sha256_hash", "sha1_hash", "md5_hash"):
            t = "hash"
        if t in buckets:
            buckets[t].append(x)
    for t in buckets:
        buckets[t].sort(key=lambda x: -(x.get("confidence_level") or 0))

    selected = []
    for t, quota in quotas.items():
        picked, seen_fam = [], set()
        for x in buckets[t]:  # 第一轮: 每个家族取一条(置信度最高者优先)
            fam = (x.get("malware_printable") or "").strip().lower()
            if fam not in seen_fam:
                seen_fam.add(fam)
                picked.append(x)
            if len(picked) >= quota:
                break
        for x in buckets[t]:  # 第二轮: 家族不足时用剩余记录补齐配额
            if len(picked) >= quota:
                break
            if x not in picked:
                picked.append(x)
        selected.extend(picked)
    return selected

# 1. 抓取 CISA 已利用漏洞库 (获取 CVE 相关数据)
print("[1/3] 正在从 CISA 获取 CVE 威胁情报...")
try:
    cisa_url = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
    cisa_res = requests.get(cisa_url, timeout=10).json()
    for item in cisa_res.get('vulnerabilities', [])[:70]:  # 取前 70 条
        text = f"Vulnerability {item['cveID']} ({item['vulnerabilityName']}) affects {item['vendorProject']} {item['product']}. Short Description: {item['shortDescription']}. Required Action: {item['requiredAction']}"
        dataset.append({
            "id": len(dataset) + 1,
            "source": "CISA KEV Catalog",
            "type": "CVE",
            "text": text
        })
except Exception as e:
    print(f"CISA 获取失败: {e}")

# 2. 抓取 MITRE ATT&CK 官方数据 (获取 APT 组织与攻击手法)
print("[2/3] 正在从 MITRE ATT&CK 获取 APT 与 攻击手法 数据...")
try:
    mitre_url = "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack.json"
    mitre_res = requests.get(mitre_url, timeout=15).json()
    
    count = 0
    for obj in mitre_res.get('objects', []):
        if count >= 70:
            break
        # 筛选 intrusion-set (APT组织) 或 attack-pattern (攻击手法)
        if obj.get('type') in ['intrusion-set', 'attack-pattern'] and obj.get('description'):
            name = obj.get('name', 'Unknown')
            desc = obj.get('description', '').replace('\n', ' ')
            # 过滤太短的描述
            if len(desc) > 100:
                text = f"Entity/Technique Name: {name}. Description: {desc[:600]}"
                dataset.append({
                    "id": len(dataset) + 1,
                    "source": "MITRE ATT&CK",
                    "type": "APT/Technique",
                    "text": text
                })
                count += 1
except Exception as e:
    print(f"MITRE 获取失败: {e}")

# 3. 抓取 ThreatFox API (获取 IOC 数据; 需要免费 Auth-Key)
print("[3/3] 正在从 ThreatFox 获取真实 IOC 威胁数据...")
threatfox_key = os.environ.get("THREATFOX_API_KEY", "").strip()
if not threatfox_key:
    print("ThreatFox 跳过: 未设置 THREATFOX_API_KEY 环境变量 (免费申请 https://auth.abuse.ch/)")
else:
    try:
        tf_url = "https://threatfox-api.abuse.ch/api/v1/"
        headers = {"Auth-Key": threatfox_key}
        tf_data = {"query": "get_iocs", "days": 7}  # days 最大 7, 取更多 IOC 以凑够 70 条
        tf_res = requests.post(tf_url, json=tf_data, headers=headers, timeout=30)
        tf_res.raise_for_status()
        tf_body = tf_res.json()
        if tf_body.get("query_status") != "ok":
            print(f"ThreatFox query_status 异常: {tf_body}")
        else:
            data = tf_body.get("data", [])
            valid = [x for x in data
                     if (x.get("malware_printable") or "").strip().lower() not in ("", "unknown malware", "unknown")]
            for item in sample_iocs(valid, 70):
                text = (f"Threat Malware {item.get('malware_printable')} associated IOC detected: "
                        f"{item.get('ioc')} (Type: {item.get('ioc_type')}). "
                        f"Threat Type: {item.get('threat_type')}. "
                        f"Confidence: {item.get('confidence_level')}%.")
                dataset.append({
                    "id": len(dataset) + 1,
                    "source": "ThreatFox API",
                    "type": "IOC/Malware",
                    "text": text,
                })
    except Exception as e:
        print(f"ThreatFox 获取失败: {e}")

# 保存为 JSON Lines 格式
output_file = "cti_200_dataset.jsonl"
with open(output_file, "w", encoding="utf-8") as f:
    for data in dataset:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")

print(f"\n收集完成！成功收集 {len(dataset)} 条威胁情报文本，已保存至文件: {output_file}")