# 统一评测说明

本目录存放独立于问答 Agent 代码的统一离线评测入口和人工评测样例。评测脚本会读取 `eval_dataset.jsonl`，逐条调用问答后端，再根据返回结果计算回答质量、检索命中、归因和拒答相关指标。

## 目录内容

| 文件 | 作用 |
|---|---|
| `run_evaluation.py` | 一键评测脚本，调用 QA API 与检索 API，生成预测结果和汇总指标。 |
| `eval_dataset.jsonl` | 正式人工评测集，当前共 50 条，覆盖 CVE、APT、IOC、归因和拒答。 |
| `evaluation_predictions.jsonl` | 评测运行后的逐题预测结果，会被重新运行覆盖。 |
| `evaluation_summary.json` | 评测运行后的汇总指标，会被重新运行覆盖。 |

## 启动前置服务

完整评测链路依赖两个后端服务：

1. 检索服务：`wjm-search/api_server.py`
2. 问答服务：`lan_shuyang_qa/run.py`

推荐从仓库根目录分别启动：

```bash
cd wjm-search
python api_server.py
```

再开一个终端：

```bash
cd lan_shuyang_qa
python3 run.py
```

服务默认地址：

| 服务 | 默认地址 | 用途 |
|---|---|---|
| 检索服务 | `http://127.0.0.1:8001/api/retrieval` | 返回候选证据、来源 id、实体和图谱路径。 |
| 问答服务 | `http://127.0.0.1:8000/api/chat` | 串联检索、归因、安全校验和答案生成。 |

可以先检查健康状态：

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8000/health
```

## 一键运行评测

从仓库根目录运行：

```bash
python unified_eval/run_evaluation.py
```

脚本默认会：

1. 读取 `unified_eval/eval_dataset.jsonl`
2. 对每道题请求 `POST http://127.0.0.1:8000/api/chat`
3. 从问答返回的 `citations` 中抽取 `retrieved_ids`
4. 计算 EM、F1、Recall@5、MRR、归因准确率、拒答准确率和置信度分析
5. 写出 `unified_eval/evaluation_predictions.jsonl`
6. 写出 `unified_eval/evaluation_summary.json`

## 常用参数

```bash
python unified_eval/run_evaluation.py \
  --dataset unified_eval/eval_dataset.jsonl \
  --predictions unified_eval/evaluation_predictions.jsonl \
  --summary unified_eval/evaluation_summary.json \
  --chat-url http://127.0.0.1:8000/api/chat \
  --retrieval-url http://127.0.0.1:8001/api/retrieval \
  --top-k 6 \
  --timeout 15
```

如果只想基于已有 `evaluation_predictions.jsonl` 重新生成汇总，不重新调用后端：

```bash
python unified_eval/run_evaluation.py --summary-only
```

## 评测数据格式

`eval_dataset.jsonl` 每行是一道题，统一 schema：

```json
{
  "id": "eval-cve-001",
  "category": "CVE",
  "question": "CVE-2026-82078 影响什么产品？",
  "gold_answer": "CVE-2026-82078 影响 NG/MF。",
  "gold_doc_ids": ["1"],
  "gold_actor": null,
  "gold_verdict": "not_applicable",
  "is_answerable": true,
  "should_refuse": false
}
```

字段含义：

| 字段 | 含义 |
|---|---|
| `id` | 样本唯一编号。 |
| `category` | 题目类别：`APT`、`CVE`、`IOC`、`attribution`、`unknown/refusal`。 |
| `question` | 输入给问答系统的问题。 |
| `gold_answer` | 人工标准答案，尽量短、明确，方便 EM/F1 和人工复核。 |
| `gold_doc_ids` | 标准证据 record id，必须来自真实知识库记录；拒答题为空列表。 |
| `gold_actor` | 涉及的威胁组织；无关题为 `null`。 |
| `gold_verdict` | 归因标签：`not_applicable`、`supported`、`inconclusive`。 |
| `is_answerable` | 当前知识库是否足够回答。 |
| `should_refuse` | 系统是否应该拒答。 |

当前正式集分布：

| category | 数量 |
|---|---:|
| `CVE` | 15 |
| `APT` | 12 |
| `IOC` | 10 |
| `attribution` | 6 |
| `unknown/refusal` | 7 |

## 评测链路

```text
eval_dataset.jsonl
  ↓
run_evaluation.py
  ↓ POST /api/chat
QA 服务 lan_shuyang_qa
  ├─ RetrievalAgent
  │    ↓ POST /api/retrieval
  │  检索服务 wjm-search
  │    ├─ Chroma 向量检索
  │    ├─ 简单关键词加权
  │    └─ 轻量知识图谱扩展
  ├─ AttributionAgent
  ├─ SafetyAgent
  └─ AnswerAgent
  ↓
逐题预测 evaluation_predictions.jsonl
  ↓
汇总指标 evaluation_summary.json
```

## 输出文件怎么看

### evaluation_predictions.jsonl

这是逐题明细，每行对应一个评测样本。除了原始 gold 字段外，脚本会补充：

| 字段 | 含义 |
|---|---|
| `prediction` | 问答系统生成的答案。 |
| `retrieved_ids` | 系统实际返回的引用证据 id。 |
| `confidence` | 问答服务返回的置信度。 |
| `refusal` | 问答服务是否拒答。 |
| `refusal_reason` | 拒答原因。 |
| `pred_actor` | 系统预测的归因 actor。 |
| `pred_verdict` | 系统预测的归因 verdict。 |
| `citations` | 完整引用证据。 |
| `error` | 请求失败时记录错误信息。 |

逐题排查时优先看：

1. `retrieved_ids` 是否命中 `gold_doc_ids`
2. `refusal` 是否等于 `should_refuse`
3. `prediction` 是否包含 `gold_answer` 的关键实体
4. attribution 题的 `pred_actor` / `pred_verdict` 是否匹配 gold

### evaluation_summary.json

这是总览指标，适合写报告和看版本变化。

常用字段：

| 字段 | 含义 | 怎么解读 |
|---|---|---|
| `overall.EM` | 精确匹配率 | 对生成式答案较严格，通常偏低。 |
| `overall.F1` | token 级 F1 | 比 EM 宽松，适合观察答案内容是否接近标准答案。 |
| `overall.Recall@5_any_hit` | 前 5 条引用是否命中 gold doc | 主要反映检索质量。 |
| `overall.MRR` | 首个命中文档的倒数排名 | 越接近 1，说明正确证据排得越靠前。 |
| `by_category` | 分类别指标 | 用来看 CVE、APT、IOC、归因、拒答哪类最弱。 |
| `attribution.actor_accuracy` | 归因 actor 准确率 | 只统计 `category=attribution`。 |
| `attribution.verdict_accuracy` | 归因 verdict 准确率 | 检查 supported/inconclusive 判断。 |
| `refusal.refusal_accuracy` | 拒答决策准确率 | 检查该答时答、该拒时拒。 |
| `refusal.false_refusal_rate` | 误拒率 | 可回答题被拒答的比例，过高说明阈值或检索偏保守。 |
| `refusal.answer_coverage` | 可回答题覆盖率 | 可回答题中成功给出答案的比例。 |
| `confidence_analysis` | 置信度分桶和阈值模拟 | 用于调 `CONFIDENCE_THRESHOLD`。 |
| `error_analysis` | 错误样本 id 分桶 | 最适合定位下一轮修复目标。 |

## 指标计算口径

- EM：`gold_answer` 和 `prediction` 分词后完全一致才算命中。
- F1：基于中英文混合 token 的重叠计算。
- Recall@5：`retrieved_ids` 前 5 个里只要有一个命中 `gold_doc_ids` 就算 1。
- MRR：第一个命中的证据越靠前分越高。
- attribution：只统计 `category == "attribution"` 的样本。
- refusal：以 `should_refuse` 为 gold，检查 API 返回的 `refusal`。
- confidence：直接使用 QA API 返回的 `confidence`，脚本只做平均、分桶和阈值模拟。

注意：生成式回答可能措辞很长，EM 往往会偏低。正式报告里建议同时看 F1、检索命中、拒答准确率和人工复核结果。

## 当前样例集设计

当前 50 条样例严格基于 `dataset/annotated_dataset.jsonl` 中的真实记录与关系：

| 类别 | 模板分布 |
|---|---|
| CVE | 影响产品 4 条、漏洞类型 4 条、厂商 3 条、组合题 2 条、链式/不完整补丁 2 条 |
| APT | 归因国家 3 条、目标行业/国家 4 条、使用软件 3 条、关联行动 2 条 |
| IOC | Domain 3 条、IP 3 条、URL 2 条、Hash 2 条 |
| attribution | supported 4 条、inconclusive 2 条 |
| unknown/refusal | 不存在实体 4 条、关系/证据不足 3 条 |

IOC 正例只考察 `IOC -> Malware`，不构造 `IOC -> APT`、`IOC -> CVE` 等当前知识库不支持的关系。

## 常见问题

### QA API 连接失败

如果输出里 `Failed samples` 很多，或 `evaluation_predictions.jsonl` 每行都有 `error`，通常是问答服务没有启动。先检查：

```bash
curl http://127.0.0.1:8000/health
```

### 检索服务没启动

问答服务会调用检索服务。如果检索服务不可用，问答后端通常会拿不到证据，导致大量拒答。检查：

```bash
curl http://127.0.0.1:8001/health
```

### 只想看旧结果

直接打开 `evaluation_summary.json` 看汇总；打开 `evaluation_predictions.jsonl` 看逐题明细。重新跑评测会覆盖这两个输出文件。

### 调阈值应该看哪里

优先看 `evaluation_summary.json` 里的：

- `refusal.false_refusal_rate`
- `refusal.answer_coverage`
- `confidence_analysis.threshold_simulation`

如果误拒率很高，说明当前拒答阈值可能过严；如果漏拒很多，说明阈值或证据判断可能过松。

