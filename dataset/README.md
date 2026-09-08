# CTI 数据集实体/关系标注

对 `cti_200_dataset.jsonl` 中的网络威胁情报文本进行**实体抽取与关系抽取**,输出面向**知识图谱构建**的结构化标注结果。全部标注由规则引擎确定性完成。

## 1. 数据概况

| 来源 | 类型 | 条数 | 文本模板 |
|---|---|---|---|
| CISA KEV Catalog | CVE | 70 | `Vulnerability CVE-... (名称) affects 厂商 产品. Short Description: ... Required Action: ...` |
| MITRE ATT&CK | APT/Technique | 70 | `Entity/Technique Name: 组织名. Description: ...`(内含 `[实体](https://attack.mitre.org/groups/Gxxxx)` / `.../software/Sxxxx` 链接) |
| ThreatFox API | IOC/Malware | 70 | `Threat Malware 恶意软件名 associated IOC detected: IOC值 (Type: 类型). Threat Type: 威胁类型. Confidence: 置信度%.` |

> 文件名中的 "200" 为收集目标数;实际文件含 210 条(70+70+70)。ThreatFox 采集需 `THREATFOX_API_KEY` 环境变量(免费申请 https://auth.abuse.ch/)。

## 2. 运行

```bash
/home/hitcrt/miniconda3/envs/shit/bin/python annotate.py
```

依赖:无(仅 `json` / `re` / `csv` 标准库)。输出三个文件:

| 文件 | 内容 |
|---|---|
| `annotated_dataset.jsonl` | 每条记录追加 `entities` / `relations` / `label` / `required_action` / `directives` / `url` / `ioc` |
| `kg_nodes.csv` | 全局去重节点(395 个),列:`node_id, label, name, attrs(JSON), record_ids` |
| `kg_edges.csv` | 全局去重边(571 条),列:`source, relation, target, method, record_ids` |

- `url`:记录主来源链接(MITRE 记录取自首条 `attack.mitre.org` 链接;CVE 记录为空串)。当前数据集无外部链接时为空。
- `ioc`:结构化 IOC `{"ips": [...], "domains": [...], "hashes": [...]}`。当前原始数据无 IOC,故基本为空;待 ThreatFox IOC 数据补齐后自然填充。

## 3. 实体类型(9 类)

| 类型 | 含义 | 关键属性 | 示例 |
|---|---|---|---|
| `Vulnerability` | CVE 漏洞 | `cve_id`, `year`, `cve_name`, `impacts[]`, `attack_position[]`, `end_of_life`, `mentioned_only` | `CVE-2026-82078` |
| `Vendor` | 厂商 | — | `Microsoft` |
| `Product` | 受影响产品 | — | `SharePoint` |
| `VulnerabilityClass` | 漏洞类型 | `cwe_id`(映射自 CWE) | `OS Command Injection` (CWE-78) |
| `ThreatActor` | 威胁组织/APT | `attck_id`(Gxxxx), `first_seen`, `motivations[]`, `attribution_details[]` | `APT38` (G0082) |
| `Software` | 恶意软件/工具 | `attck_id`(Sxxxx) | `Dridex` (S0384) |
| `Country` | 国家/地区(含大区) | — | `North Korea`, `Middle East` |
| `Sector` | 受害行业 | — | `Financial`, `Critical Infrastructure` |
| `Campaign` | 行动/战役 | — | `Operation Aurora` |

每个实体带 `spans`:该实体在原文中的全部字符偏移 `[[start, end], ...]`。记录级 `label` 字段为扁平化的 NER 格式 `[[start, end, 类型], ...]`(按位置排序)。

## 4. 关系类型(10 类)

| 关系 | 方向 | 适用 | 抽取方式 |
|---|---|---|---|
| `affects` | Vulnerability → Product | CVE | 模板(必中) |
| `developed_by` | Product → Vendor | CVE | 模板(必中) |
| `has_class` | Vulnerability → VulnerabilityClass | CVE | 模板 + 名称回退 |
| `chained_with` | Vulnerability → Vulnerability | CVE | 显式("can be chained with") |
| `incomplete_patch_of` | Vulnerability → Vulnerability | CVE | 显式("result of an incomplete patch for") |
| `uses` | ThreatActor → Software | MITRE | 同记录共现 |
| `attributed_to` | ThreatActor → Country | MITRE | 归因短语(如 "North Korean state-sponsored") |
| `targets` | ThreatActor → Country / Sector | MITRE | 句子级语境判断 |
| `related_to` | ThreatActor↔ThreatActor / Software↔Software | MITRE | 同记录共现 |
| `associated_with` | ThreatActor → Campaign | MITRE | 显式("Operation X") |

每条关系带 `method` 字段标示置信度:`template` / `explicit` > `attribution_pattern` > `co-occurrence`。

## 5. 输出格式示例

```json
{
  "id": 1, "source": "CISA KEV Catalog", "type": "CVE", "text": "...",
  "entities": [
    {"id": "e1", "type": "Vulnerability", "name": "CVE-2026-82078",
     "attrs": {"cve_id": "CVE-2026-82078", "year": 2026,
               "cve_name": "PaperCut NG/MF Unsafe Reflection Vulnerability",
               "impacts": ["Remote Code Execution", "Unauthorized Access"],
               "attack_position": [], "end_of_life": false, "mentioned_only": false},
     "spans": [[14, 28]]},
    {"id": "e2", "type": "VulnerabilityClass", "name": "Unsafe Reflection",
     "attrs": {"cwe_id": "CWE-470"}, "spans": [[45, 62], [148, 165]]}
  ],
  "relations": [
    {"head": "e1", "type": "has_class", "tail": "e2", "method": "template"},
    {"head": "e1", "type": "chained_with", "tail": "e5", "method": "explicit"}
  ],
  "url": "",
  "ioc": {"ips": [], "domains": [], "hashes": []}
}
```

`impacts` 取值:`Remote Code Execution` / `Denial of Service` / `Privilege Escalation` / `Information Disclosure` / `Authentication Bypass` / `Arbitrary File Manipulation` / `Unauthorized Access` / `Server-Side Request Forgery`。
`attack_position` 取值:`unauthenticated` / `authenticated` / `remote` / `local` / `network`。

## 6. 标注统计

| 指标 | 数量 |
|---|---|
| 记录总数 | 210(0 条告警) |
| 实体总数 / 去重节点 | 784 / **438** |
| 关系总数 / 去重边 | 584 / **571** |
| 实体 span 总数 | 1335(与原文全部精确对齐) |

主要实体分布:Sector 160、Country 157、Software 89(19 MITRE + 70 ThreatFox,70 条 ThreatFox 覆盖 44 个恶意软件家族)、ThreatActor 81、Vulnerability 76(70 主记录 + 6 链式提及)、VulnerabilityClass/Vendor/Product 各 70、Campaign 11。

## 7. 知识图谱导入(Neo4j 示例)

```cypher
LOAD CSV WITH HEADERS FROM 'file:///kg_nodes.csv' AS row
CREATE (n {node_id: row.node_id})
SET n:Entity, n.label = row.label, n.name = row.name,
    n.attrs = apoc.convert.fromJsonMap(row.attrs);

LOAD CSV WITH HEADERS FROM 'file:///kg_edges.csv' AS row
MATCH (a {node_id: row.source}), (b {node_id: row.target})
CALL apoc.merge.relationship(a, row.relation, {}, {}, b) YIELD rel
RETURN count(*);
```

(需 APOC 插件;无 APOC 时可改用动态 `apoc.merge.relationship` 或按关系类型分别 `MERGE`。)
节点 ID 规则:`CVE:CVE-xxx`、`ATT&CK:Gxxxx` / `ATT&CK:Sxxxx`、`VENDOR:名称`、`COUNTRY:名称` 等,跨记录同实体自动合并。

## 8. 已知限制

- **id 67**(LiteSpeed symlink)源文本截断、无影响描述,`impacts` 如实为空。
- MITRE 侧 `uses` / `related_to` 为同记录共现推断,非显式陈述;`targets` 依赖语境词(如 targeted/victims/against),少数段落无此语境时会漏抽目标行业。
- 无 ATT&CK ID 的软件名(如 Hades、LockBit、远程工具)未建实体。
- `targets` 关系中 Sector 与 Country 共用同一关系类型,可用目标节点 `label` 区分。
- 未包含 ThreatFox IOC/Malware 数据(当前 140 条;ThreatFox 现要求免费 `Auth-Key`,见下方扩展方向)。

## 9. 扩展方向

- 用 DeepSeek API 对规则结果做 LLM 复核/补漏(环境已有 `DEEPSEEK_API_KEY`),重点补:无 ID 软件名、TTP(technique)关系、更细的归因。
- 补齐 ThreatFox 的 70 条 IOC 数据以达 200 条目标:ThreatFox API 现已要求 `Auth-Key` 请求头,在 https://auth.abuse.ch/ 免费申请后,以 `THREATFOX_API_KEY=xxx python climb.py` 重跑采集(已改为 `days:7` 以获取足够 IOC);`annotate.py` 已支持 `IOC/Malware` 记录(恶意软件名建 `Software` 实体,IOC 值落入记录级 `ioc` 字段)。
