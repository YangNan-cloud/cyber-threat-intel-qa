# 兰书阳：大模型问答与多智能体协作

本目录仅包含问答后端，不包含数据采集、向量/图谱检索实现、评测总报告或 Streamlit 页面；它们分别由其他成员维护。

## 启动

```powershell
cd lan_shuyang_qa
Copy-Item .env.example .env
pip install -r requirements.txt
python run.py
```

健康检查：`GET http://127.0.0.1:8000/health`。

## 配置

所有可修改配置都在 `.env`：`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、`RETRIEVAL_URL`、`CONFIDENCE_THRESHOLD`、`HOST`、`PORT`。不要提交真实密钥。

## 对其他成员的最小接口

### 依赖成员2：检索服务

`POST $RETRIEVAL_URL` 请求：

```json
{"query":"APT29 最近使用什么手法？","top_k":6}
```

响应：

```json
{"results":[{"id":"doc-1","text":"片段内容","source":"CISA","url":"https://...","score":0.92,"entities":{"actors":["APT29"]},"graph_paths":["APT29 -> T1078 -> IOC"]}]}
```

`score` 必须归一化到 0–1；其余字段缺失时系统会安全降级。

### 提供给成员4、5：问答服务

`POST /api/chat`：

```json
{"query":"CVE-2024-xxxx 的修复建议是什么？","top_k":6,"conversation_id":"可选会话ID"}
```

返回 `answer`、`citations`、`entities`、`attribution`、`confidence`、`refusal`、`refusal_reason` 和 `conversation_id`。当无证据、归因不充分或置信度低于阈值时，`refusal=true`，禁止将回答展示为确定性结论。

## Agent 逻辑

`RetrievalAgent` 调用成员2的检索；`AttributionAgent` 只在多条来源及图谱证据支持时确认归因；`SafetyAgent` 基于检索分数、独立来源、图谱路径与归因风险给出置信度和拒答；`AnswerAgent` 使用 DeepSeek 生成带 `[来源编号]` 的结论、取证与修复建议，API 不可用时仅输出证据型降级答案。
