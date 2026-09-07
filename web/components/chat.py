import streamlit as st


def render_chat_history():
    """渲染多轮会话历史"""
    messages = st.session_state.get("messages", [])

    if not messages:
        st.caption("暂无对话记录，开始提问吧！")
        return

    for msg in messages:
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.markdown(msg["content"])
        else:
            with st.chat_message("assistant"):
                st.markdown(msg["content"])
