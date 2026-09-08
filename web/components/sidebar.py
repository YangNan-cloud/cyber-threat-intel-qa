import streamlit as st
from utils.session_manager import export_dialogue, clear_session


def render_sidebar():
    with st.sidebar:
        st.title("🛡️ 威胁情报助手")
        st.caption("网络开源威胁情报智能问答系统")
        st.divider()

        # 对话历史列表
        st.subheader("📄 对话历史")
        messages = st.session_state.get("messages", [])
        if messages:
            for idx, msg in enumerate(messages[-10:]):  # 只显示最近10条
                if msg["role"] == "user":
                    st.caption(f"👤 {msg['content'][:30]}...")
                else:
                    st.caption(f"🤖 {msg['content'][:30]}...")
        else:
            st.caption("暂无对话记录")

        st.divider()

        if st.button("📤 导出对话记录"):
            json_str = export_dialogue()
            st.download_button(
                label="下载JSON",
                data=json_str,
                file_name="dialogue_export.json",
                mime="application/json"
            )

        if st.button("🗑️ 清空对话"):
            clear_session()
            st.rerun()

        st.divider()
        st.caption("v1.0 | 课程项目")
