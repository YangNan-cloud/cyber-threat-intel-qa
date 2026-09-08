# config.py
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 向量数据库配置
VECTOR_DB_PATH = os.path.join(BASE_DIR, "vector_db")
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
COLLECTION_NAME = "threat_intel_collection"

# 检索参数
TOP_K_VECTOR = 5
TOP_K_GRAPH = 3

# ========== 真实CTI数据集路径（jsonl） ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
CTI_ANNOTATED_JSONL = os.path.join(PROJECT_ROOT, "dataset", "annotated_dataset.jsonl")

# 图谱持久化
KG_SAVE_PATH = os.path.join(BASE_DIR, "kg_data/kg_graph.json")

# API服务配置
API_HOST = "0.0.0.0"
API_PORT = 8001