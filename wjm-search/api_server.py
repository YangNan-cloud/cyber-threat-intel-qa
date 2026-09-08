# api_server.py
from fastapi import FastAPI
from pydantic import BaseModel
from hybrid_retriever import HybridRetriever
from config import API_HOST, API_PORT

app = FastAPI(title="威胁情报混合检索&知识图谱服务")
retriever = HybridRetriever()

# ========== 适配兰书阳模块的请求模型：字段为 query、top_k ==========
class RetrievalRequest(BaseModel):
    query: str
    top_k: int = 6


def _handle_retrieval(req: RetrievalRequest):
    """
    【对外接口，供兰书阳 RetrievalAgent调用】
    协议按照lan_shuyang_qa/README.txt定义
    请求: {"query":"xxx","top_k":6}
    返回: {"results": [{"id":"","text":"","source":"","score":0~1,"entities":{},"graph_paths":[]}]}
    """
    # 调用内部原有混合检索逻辑（内核完全不变）
    inner_result = retriever.retrieve(user_query=req.query, top_k_total=req.top_k)

    graph_expand_entities = inner_result["graph_expand_entities"]
    candidates = inner_result["candidates"]

    results = []
    for cand in candidates:
        meta = cand["metadata"]
        source_id = meta.get("source_id", "")
        text_chunk = cand["chunk_text"]
        score = cand["final_score"]
        # source来源：数据集原始没有url，取source_id作为来源标识
        source = f"record:{source_id}"

        # 解析元数据内json字符串实体
        import json
        actors = []
        try:
            actors_raw = json.loads(meta.get("apt_entities", "[]"))
            actors = [x["name"] for x in actors_raw]
        except Exception:
            pass

        cve_list = []
        try:
            cve_raw = json.loads(meta.get("cve_entities", "[]"))
            cve_list = [x["name"] for x in cve_raw]
        except Exception:
            pass

        entities_out = {
            "actors": actors,
            "cves": cve_list
        }

        # 组装简单graph_paths：当前轻量图谱，构造实体关联路径示例
        graph_paths = []
        for ent_name in graph_expand_entities:
            graph_paths.append(f"{ent_name} <-> related")

        item = {
            "id": source_id,
            "text": text_chunk,
            "source": source,
            "score": round(float(score),4),
            "entities": entities_out,
            "graph_paths": graph_paths
        }
        results.append(item)

    return {"results": results}


@app.post("/api/retrieval")
def retrieval_api(req: RetrievalRequest):
    return _handle_retrieval(req)


@app.post("/search")
def legacy_retrieval_api(req: RetrievalRequest):
    return _handle_retrieval(req)


@app.get("/health")
def health_check():
    return {"status":"ok","module":"retrieval_graphrag"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)