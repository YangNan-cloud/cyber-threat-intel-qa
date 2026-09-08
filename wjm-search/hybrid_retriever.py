# hybrid_retriever.py
from embedding_store import VectorStore
from knowledge_graph import ThreatKnowledgeGraph
import re

class HybridRetriever:
    def __init__(self):
        self.vs = VectorStore()
        self.tkg = ThreatKnowledgeGraph()
        self.tkg.load_graph()

    def keyword_search(self, query:str, raw_chunks:list):
        """简单关键词匹配，对query里面的IOC/CVE/APT实体做关键词命中"""
        hits = []
        q_tokens = re.split(r"[，。 、?？]", query)
        for item in raw_chunks:
            cnt = sum([1 for t in q_tokens if t and t in item["chunk_text"]])
            if cnt>0:
                item["keyword_hit_count"] = cnt
                hits.append(item)
        return hits

    def graph_expand_query(self, query:str):
        """从query提取实体，图谱扩展，拿到关联实体，补充检索"""
        expand_entities = set()
        for ent_name in self.tkg.entities.keys():
            if ent_name in query:
                expand_entities.add(ent_name)
                neighbors = self.tkg.query_entity_neighbor(ent_name)
                for n in neighbors:
                    expand_entities.add(n["target"])
        return list(expand_entities)

    def retrieve(self, user_query:str, top_k_total=8):
        """
        对外主函数：混合检索入口
        返回: list[dict] 候选文档片段，包含score、来源元数据、图谱扩展实体
        """
        #1向量检索
        vec_res = self.vs.vector_search(user_query)
        #2关键词增强
        kw_res = self.keyword_search(user_query, vec_res)
        #3图谱扩展实体
        expand_ents = self.graph_expand_query(user_query)

        #简单加权融合打分
        candidate_dict = {}
        for item in vec_res:
            sid = item["metadata"]["source_id"] + "||" + item["chunk_text"][0:120]
            base_score = item["score"]
            #关键词命中加分
            hit_cnt = item.get("keyword_hit_count",0)
            final_score = base_score + 0.12 * hit_cnt
            candidate_dict[sid] = {**item, "final_score":final_score}

        candidates = list(candidate_dict.values())
        candidates.sort(key=lambda x:x["final_score"], reverse=True)
        final_out = candidates[:top_k_total]

        return {
            "query": user_query,
            "graph_expand_entities": expand_ents,
            "candidates": final_out
        }

if __name__ == "__main__":
    hr = HybridRetriever()
    res = hr.retrieve("APT29使用了哪些攻击手法")
    print("图谱扩展实体：", res["graph_expand_entities"])
    for c in res["candidates"]:
        print(f'score={c["final_score"]:.3f}, text={c["chunk_text"][0:150]}')