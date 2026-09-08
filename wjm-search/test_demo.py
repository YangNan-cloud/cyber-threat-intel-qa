# test_demo.py
"""模块独立调试入口，仅读取真实 annotated_dataset.jsonl"""
from data_loader import load_cti_jsonl, extract_entities_relations
from chunker import split_text_chunk, build_chunk_metadata
from embedding_store import VectorStore
from knowledge_graph import build_graph_from_dataset
from hybrid_retriever import HybridRetriever
from config import CTI_ANNOTATED_JSONL   # ← 补上这一行导入


def build_all():
    # 加载真实CTI标注数据集
    data = load_cti_jsonl()
    if len(data) == 0:
        raise FileNotFoundError(f"未加载到annotated_dataset.jsonl，请检查路径：{CTI_ANNOTATED_JSONL}，确认文件存在！")

    print(f">>> 成功加载真实CTI标注数据集，共 {len(data)} 条记录")

    # 构建知识图谱
    build_graph_from_dataset(data)
    print("知识图谱构建完成并持久化")

    # 文本分块，写入向量库
    vs = VectorStore()
    all_chunks = []
    all_meta = []
    all_ids = []
    for idx, item in enumerate(data):
        text = item["text"]
        chunks = split_text_chunk(text)
        for cid, ck in enumerate(chunks):
            meta = build_chunk_metadata(item, ck)
            uid = f"doc_{idx}_chunk_{cid}"
            all_chunks.append(ck)
            all_meta.append(meta)
            all_ids.append(uid)
    vs.add_documents(all_chunks, all_meta, all_ids)
    print(f"向量库写入完成，共{len(all_ids)}个chunk")


def test_query():
    hr = HybridRetriever()
    query = "APT38 使用了什么软件"
    out = hr.retrieve(query)
    print(f"\n用户问题：{out['query']}")
    print(f"图谱扩展实体：{out['graph_expand_entities']}")
    for idx, cand in enumerate(out["candidates"]):
        print(f"\n====候选{idx+1} score={cand['final_score']:.3f}====")
        print(cand["chunk_text"][0:220])


if __name__ == "__main__":
    build_all()
    test_query()