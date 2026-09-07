import streamlit as st
import json
from datetime import datetime


def init_session():
    """初始化会话状态"""
    if "messages" not in st.session_state:
        st.session_state.messages = []  # [{"role": "user/assistant", "content": "..."}]
    if "current_response" not in st.session_state:
        st.session_state.current_response = None
    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = None
    if "evaluation_metrics" not in st.session_state:
        st.session_state.evaluation_metrics = {}


def add_message(role: str, content: str):
    """添加对话消息"""
    st.session_state.messages.append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })


def get_conversation_id():
    """获取当前会话id"""
    return st.session_state.get("conversation_id")


def set_conversation_id(cid: str):
    """设置会话id"""
    st.session_state.conversation_id = cid


def export_dialogue() -> str:
    """导出对话记录为JSON"""
    return json.dumps(st.session_state.messages, ensure_ascii=False, indent=2)


def clear_session():
    """清空所有会话状态"""
    st.session_state.messages = []
    st.session_state.current_response = None
    st.session_state.conversation_id = None
