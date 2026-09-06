# test_demo.py
"""模块独立调试入口，不需要启动web服务，直接运行即可测试向量库、图谱、混合检索"""
from data_loader import load_threat_json
from chunker import split_text_chunk, build_chunk_metadata
from embedding_store import VectorStore
from knowledge_graph import build_graph_from_dataset
from hybrid_retriever import HybridRetriever

def build_all():
    #1读取数据集（李佳颖输出的威胁情报json）
    data = load_threat_json()
    if len(data)==0:
        print("警告：未读取到威胁情报数据集，请检查路径 ../dataset/threat_intel_kg.json")
        return
    #2构建知识图谱
    build_graph_from_dataset(data)
    print("知识图谱构建完成并持久化")

    #3分块+写入向量库
    vs = VectorStore()
    all_chunks = []
    all_meta = []
    all_ids = []
    for idx,item in enumerate(data):
        text = item["text"]
        chunks = split_text_chunk(text)
        for cid,ck in enumerate(chunks):
            meta = build_chunk_metadata(item, ck)
            uid = f"doc_{idx}_chunk_{cid}"
            all_chunks.append(ck)
            all_meta.append(meta)
            all_ids.append(uid)
    vs.add_documents(all_chunks, all_meta, all_ids)
    print(f"向量库写入完成，共{len(all_ids)}个chunk")

def test_query():
    hr = HybridRetriever()
    query = "APT29使用了哪些攻击手法"
    out = hr.retrieve(query)
    print(f"\n用户问题：{out['query']}")
    print(f"图谱扩展实体：{out['graph_expand_entities']}")
    for idx,cand in enumerate(out["candidates"]):
        print(f"\n====候选{idx+1} score={cand['final_score']:.3f}====")
        print(cand["chunk_text"][0:220])

if __name__ == "__main__":
    # 第一次运行打开build_all，后续调试注释，避免重复入库
    build_all()
    test_query()