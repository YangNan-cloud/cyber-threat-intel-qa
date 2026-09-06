# embedding_store.py
import os
# 增加镜像地址
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
import chromadb
from chromadb.utils import embedding_functions
from config import *
import json

class VectorStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
        self.emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL_NAME)
        self.collection = self.client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=self.emb_fn)

    def add_documents(self, chunk_texts:list, metadatas:list, ids:list):
        """批量写入向量库"""
        self.collection.add(
            documents=chunk_texts,
            metadatas=metadatas,
            ids=ids
        )

    def vector_search(self, query:str, top_k=TOP_K_VECTOR):
        """向量检索，返回结果列表"""
        result = self.collection.query(
            query_texts=[query],
            n_results=top_k
        )
        out = []
        for idx,doc in enumerate(result["documents"][0]):
            meta = result["metadatas"][0][idx]
            dist = result["distances"][0][idx]
            out.append({
                "chunk_text": doc,
                "metadata": meta,
                "distance": dist,
                "score": 1.0 - dist #转为相似度分数
            })
        return out

    def clear_collection(self):
        self.client.delete_collection(COLLECTION_NAME)

if __name__ == "__main__":
    vs = VectorStore()
    print("向量库初始化完成")