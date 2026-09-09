import streamlit as st


def render_chat_history():
    """渲染多轮会话历史"""
    messages = st.session_state.get("messages", [])

    # 检查是否有需要滚动到的消息
    scroll_to_idx = st.session_state.get("scroll_to_message", None)

    if not messages:
        st.caption("暂无对话记录，开始提问吧！")
        return

    # 渲染所有消息
    for idx, msg in enumerate(messages):
        msg_id = f"msg-{idx}"
        st.markdown(f'<div id="{msg_id}" style="scroll-margin-top: 80px;"></div>', unsafe_allow_html=True)

        if msg["role"] == "user":
            with st.chat_message("user"):
                st.markdown(msg["content"])
        else:
            with st.chat_message("assistant"):
                st.markdown(msg["content"])

    # 如果需要滚动，使用更强大的 JavaScript
    if scroll_to_idx is not None and scroll_to_idx < len(messages):
        js_code = f"""
        <script>
            (function() {{
                const targetId = 'msg-{scroll_to_idx}';
                let attempts = 0;
                const maxAttempts = 20;

                function tryScroll() {{
                    const element = document.getElementById(targetId);
                    if (element) {{
                        console.log('Found element, scrolling to:', targetId);
                        element.scrollIntoView({{ behavior: 'smooth', block: 'center' }});

                        // 高亮
                        element.style.transition = 'background-color 0.5s ease';
                        element.style.backgroundColor = '#ffff99';
                        setTimeout(() => {{
                            element.style.backgroundColor = 'transparent';
                        }}, 2000);
                        return true;
                    }}
                    attempts++;
                    if (attempts < maxAttempts) {{
                        console.log(`Attempt ${{attempts}}/${{maxAttempts}} - element not found, retrying...`);
                        setTimeout(tryScroll, 200);
                    }} else {{
                        console.log('Max attempts reached, element not found');
                    }}
                    return false;
                }}

                // 监听 DOM 变化
                const observer = new MutationObserver(() => {{
                    if (document.getElementById(targetId)) {{
                        observer.disconnect();
                        setTimeout(tryScroll, 100);
                    }}
                }});
                observer.observe(document.body, {{
                    childList: true,
                    subtree: true
                }});

                // 立即尝试
                setTimeout(tryScroll, 100);
                setTimeout(tryScroll, 300);
                setTimeout(tryScroll, 500);
                setTimeout(tryScroll, 1000);
            }})();
        </script>
        """
        st.markdown(js_code, unsafe_allow_html=True)

        # 清除滚动标记
        st.session_state.scroll_to_message = None
