# 检索系统与知识图谱
模块职责：向量检索、轻量 GraphRAG 知识图谱、混合检索服务，对外提供 HTTP 检索接口，供多智能体问答模块调用。

## 1 目录结构
retrieval_graphrag/ 

├── config.py     &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;           # 全局配置：向量库路径、embedding模型、数据集路径、服务端口

├── data_loader.py      &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;     # 读取CTI标注数据集annotated_dataset.jsonl，完成实体ID→名称映射转换

├── chunker.py           &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;    # 文本滑动窗口分块、构造检索块元数据

├── embedding_store.py    &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;   # Chroma向量库封装：向量化入库、向量检索

├── knowledge_graph.py     &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  # 轻量内存知识图谱实现，实体‑关系持久化、实体邻居查询

├── hybrid_retriever.py    &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  # 混合检索核心：向量检索+关键词增强+图谱实体扩展

├── api_server.py          &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  # FastAPI对外HTTP服务，对齐问答Agent接口协议

├── evaluate_retrieval.py   &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; # 检索评测脚本：Recall@K、MRR指标计算

├── test_demo.py           &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;  # 本地独立调试脚本（不启动Web服务，完成数据集加载、入库、检索测试）

├── vector_db/            &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;   # Chroma持久化向量数据库目录（运行后自动生成）

└── kg_data/              &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;   # 知识图谱持久化目录，kg_graph.json存储实体与关系

## 2 环境依赖
```bash
pip install fastapi uvicorn chromadb sentence-transformers pydantic pandas numpy
```
模型说明：默认使用all‑MiniLM‑L6‑v2作为 Embedding 模型；网络环境差可使用本地离线模型，修改config.py中EMBED_MODEL_NAME为本地模型路径。

## 3 数据集说明
本模块读取李佳颖输出的标注结果文件：annotated_dataset.jsonl

1.原始数据集共 140 条 CTI 威胁情报记录，来源 CISA KEV Catalog、MITRE ATT&CK；  
2.原始 jsonl 内部 relations 使用实体 ID（e1/e2）作为 head/tail；data_loader.py自动完成 ID 到实体 name 映射转换，适配图谱构建；  
3.实体类型：ThreatActor(APT 威胁组织)、Vulnerability(CVE 漏洞)、Software、Vendor、Product、Country、Sector等；  
4.关系类型：uses、affects、targets、attributed_to、related_to等；  
5.当前数据集限制：缺少 IOC/Malware 数据；后续补齐 ThreatFox 抓取数据后可扩展解析逻辑。  

配置文件config.py中CTI_ANNOTATED_JSONL指定数据集完整路径；建议调试阶段使用绝对路径，规避 Windows 相对路径工作目录问题。


## 4 运行流程
步骤 1：数据集入库，构建向量库 + 知识图谱  
```bash
pip install fastapi uvicorn chromadb sentence-transformers pydantic pandas numpy
```  
(1)读取annotated_dataset.jsonl；  
(2)完成实体‑关系转换，构建知识图谱并持久化；  
(3)文本滑动窗口分块，向量化写入 Chroma 向量数据库；  
(4)执行本地检索测试，验证内核逻辑。  
注意：切换新版本数据集前，务必手动删除vector_db、kg_data目录，清除旧缓存


步骤 2：启动检索 HTTP 服务  

```bash
python api_server.py
```  
服务监听地址：http://127.0.0.1:8001  
接口文档地址：http://127.0.0.1:8001/docs  
健康检查接口：GET http://127.0.0.1:8001/health  
  
返回示例  
```json
{"status":"ok","module":"retrieval_graphrag"}
```
接口协议严格对齐lan_shuyang_qa/README.txt约定。  
  
请求体  
```json
{
  "query":"APT38 使用了什么软件",
  "top_k":6
}
```
  
响应返回格式  
```json
{
  "results": [
    {
      "id": "3",
      "text": "原始威胁情报文本片段",
      "source": "record:3",
      "url": "",
      "score": 0.7642,
      "entities": {
        "actors": ["APT38"],
        "cves": []
      },
      "graph_paths": ["APT38 <-> uses <-> Dridex"]
    }
  ]
}
```

字段说明  

| 字段       | 说明                                                              |
|----------|-----------------------------------------------------------------|
| `id`     | 检索片段对应的原始记录 id |
| `text`   | 检索返回文本块内容             |
| `source` | 数据来源标识，数据集无原始 url，格式record:{记录id}               |
| `url`    | 原始数据集无链接，为空字符串，上层问答模块安全降级处理   |
| `score`  | 混合检索综合得分，0‑1 归一化，分数越高相关性越高   |
| `entities.actors` | 片段中提取的威胁组织 / APT 列表   |
| `entities.cves` | 片段中提取的 CVE 漏洞编号列表   |
| `graph_paths` | 由知识图谱扩展得到的实体关联路径字符串   |  
  
## 5 模块内部逻辑说明  
  
1.文本分块：滑动窗口分块，配置 chunk_size、overlap，对原始威胁情报文本做切分；
2.向量检索：Chroma + Sentence‑Transformer Embedding，计算文本语义相似度；
3.关键词增强检索：对用户 query 做简单分词命中，对检索结果做分数加权；
4.GraphRAG 图谱扩展：识别 query 中出现的实体，查询知识图谱拿到关联实体，扩充检索上下文；  
5.混合检索打分：向量相似度分数 + 关键词命中加权，输出排序后的候选片段；  
6.API 层适配：内核逻辑不变，仅在接口层做字段转换，输出与问答 Agent 约定的 JSON 格式。  
  
## 7 已知限制  
  
1.使用轻量 JSON 内存图谱，非 Neo4j；图谱路径为简单拼接字符串，适合课程项目演示；后续可替换 Neo4j，对外接口无需改动；
2.原始数据集缺少 IOC 数据，entities暂不返回 IOC 字段；待补齐 ThreatFox IOC 数据后扩展解析；
3.原始数据集没有外部 url 链接，url字段返回空，问答模块做安全降级；
4.知识图谱关系来源于标注脚本输出，关系质量受标注规则约束。