import streamlit as st


def render_chat_history():
    """渲染多轮会话历史"""
    messages = st.session_state.get("messages", [])

    if not messages:
        st.caption("暂无对话记录，开始提问吧！")
        return

    for idx, msg in enumerate(messages):
        # 为每条消息生成唯一锚点 ID
        msg_id = f"msg-{idx}"

        if msg["role"] == "user":
            # 用户消息带锚点
            st.markdown(f'<div id="{msg_id}"></div>', unsafe_allow_html=True)
            with st.chat_message("user"):
                st.markdown(msg["content"])
        else:
            # 助手消息带锚点
            st.markdown(f'<div id="{msg_id}"></div>', unsafe_allow_html=True)
            with st.chat_message("assistant"):
                st.markdown(msg["content"])
