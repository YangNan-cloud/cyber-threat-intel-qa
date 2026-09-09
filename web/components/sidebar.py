import streamlit as st
from utils.session_manager import export_dialogue, clear_session


def render_sidebar():
    with st.sidebar:
        st.title("🛡️ 威胁情报助手")
        st.caption("网络开源威胁情报智能问答系统")
        st.divider()

        # ========== 对话历史列表（可滚动区域） ==========
        st.subheader("📄 对话历史")

        messages = st.session_state.get("messages", [])

        # 使用容器固定高度，超出滚动
        history_container = st.container(height=500)

        with history_container:
            if messages:
                # 显示全部消息
                for idx, msg in enumerate(messages):
                    # 为每条消息生成唯一 key
                    msg_key = f"msg_{idx}_{msg['role']}"

                    if msg["role"] == "user":
                        display_text = msg["content"][:50] + "..." if len(msg["content"]) > 50 else msg["content"]

                        # 在按钮上方添加细微分隔线（视觉上区分不同消息）
                        st.markdown(f"""
                        <div style="
                            border-left: 3px solid #ff4b4b;
                            margin-top: -6px;
                            margin-bottom: 6px;
                            padding: 0px 8px;
                            font-size: 11px;
                            color: #888;
                        ">
                            用户 · {msg.get('timestamp', '').split('T')[0] if msg.get('timestamp') else ''}
                        </div>
                        """, unsafe_allow_html=True)

                        # 整个卡片作为按钮
                        if st.button(
                                label=f"👤 {display_text}",
                                key=f"jump_{msg_key}",
                                use_container_width=True,
                        ):
                            # 使用 JavaScript 锚点跳转
                            st.html(f"""
                            <script>
                                var element = document.getElementById('msg-{idx}');
                                if (element) {{
                                    element.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                                }}
                            </script>
                            """, unsafe_allow_javascript=True)
                    else:
                        display_text = msg["content"][:50] + "..." if len(msg["content"]) > 50 else msg["content"]

                        st.markdown(f"""
                        <div style="
                            border-left: 3px solid #1a73e8;
                            margin-top: -6px;
                            margin-bottom: 6px;
                            padding: 0px 8px;
                            font-size: 11px;
                            color: #888;
                        ">
                            助手 · {msg.get('timestamp', '').split('T')[0] if msg.get('timestamp') else ''}
                        </div>
                        """, unsafe_allow_html=True)

                        if st.button(
                                label=f"🤖 {display_text}",
                                key=f"jump_{msg_key}",
                                use_container_width=True,
                        ):
                            st.html(f"""
                            <script>
                                var element = document.getElementById('msg-{idx}');
                                if (element) {{
                                    element.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                                }}
                            </script>
                            """, unsafe_allow_javascript=True)
            else:
                st.caption("暂无对话记录")

        st.divider()

        # ========== 底部固定区域 ==========
        bottom_container = st.container()
        with bottom_container:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📤 导出", use_container_width=True, help="导出对话记录为JSON文件"):
                    json_str = export_dialogue()
                    st.download_button(
                        label="✅ 下载JSON",
                        data=json_str,
                        file_name="dialogue_export.json",
                        mime="application/json",
                        key="download_btn"
                    )
            with col2:
                if st.button("🗑️ 清空", use_container_width=True, help="清空所有对话记录"):
                    clear_session()
                    st.rerun()

            st.divider()
            st.caption("v1.0 | 课程项目")