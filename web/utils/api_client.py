import requests
import streamlit as st

BACKEND_URL = "http://127.0.0.1:8000"


def query_backend(question: str, context: str = None, conversation_id: str = None, top_k: int = 6):
    """
    调用问答服务
    """
    url = f"{BACKEND_URL}/api/chat"

    # 如果有上传文件内容，拼接到问题中
    full_query = question
    if context:
        full_query = f"{question}\n\n[上传文件内容]\n{context[:200000]}"

    payload = {
        "query": full_query,
        "top_k": top_k,
        "conversation_id": conversation_id,
    }

    try:
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("⚠️ 问答服务未启动，请先运行 `python run.py` 启动后端")
        return None
    except requests.exceptions.Timeout:
        st.error("⏰ 请求超时，请稍后重试")
        return None
    except Exception as e:
        st.error(f"❌ 请求失败: {str(e)}")
        return None
