# knowledge_graph.py
import json
import os
from config import KG_SAVE_PATH

class ThreatKnowledgeGraph:
    def __init__(self):
        self.entities = dict() # key:实体名, value:etype
        self.relations = [] # [{"head":"","rel":"","tail":""}]

    def add_entity(self, ename:str, etype:str):
        self.entities[ename] = etype

    def add_relation(self, head:str, rel:str, tail:str):
        self.relations.append({"head":head,"rel":rel,"tail":tail})

    def query_entity_neighbor(self, entity_name:str):
        """图谱检索：查询该实体所有相连关系，GraphRAG关联检索"""
        res = []
        for r in self.relations:
            if r["head"] == entity_name:
                res.append({"direction":"out", "rel":r["rel"], "target":r["tail"], "target_type":self.entities.get(r["tail"],"unknown")})
            if r["tail"] == entity_name:
                res.append({"direction":"in", "rel":r["rel"], "target":r["head"], "target_type":self.entities.get(r["head"],"unknown")})
        return res

    def save_graph(self):
        os.makedirs(os.path.dirname(KG_SAVE_PATH), exist_ok=True)
        dump_data = {"entities":self.entities, "relations":self.relations}
        with open(KG_SAVE_PATH,"w",encoding="utf‑8") as f:
            json.dump(dump_data,f,ensure_ascii=False,indent=2)

    def load_graph(self):
        if not os.path.exists(KG_SAVE_PATH):
            return
        with open(KG_SAVE_PATH,"r",encoding="utf‑8") as f:
            d = json.load(f)
            self.entities = d["entities"]
            self.relations = d["relations"]

def build_graph_from_dataset(data):
    """从数据集构建图谱，调用data_loader输出的实体关系"""
    from data_loader import extract_entities_relations
    tkg = ThreatKnowledgeGraph()
    entity_list, rel_list = extract_entities_relations(data)
    for e in entity_list:
        tkg.add_entity(e["ename"], e["etype"])
    for r in rel_list:
        tkg.add_relation(r["head"], r["rel"], r["tail"])
    tkg.save_graph()
    return tkg

if __name__ == "__main__":
    tkg = ThreatKnowledgeGraph()
    tkg.load_graph()
    neighbors = tkg.query_entity_neighbor("APT29")
    print(neighbors)