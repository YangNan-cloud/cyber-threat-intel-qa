import streamlit as st
from components.chat import render_chat_history
from components.evaluation import render_evaluation
from components.ioc_display import render_iocs
from components.sidebar import render_sidebar
from streamlit import query_params
from utils.api_client import query_backend
from utils.file_parser import parse_file
from utils.mock_response import get_mock_response
from utils.session_manager import init_session, add_message, get_conversation_id, set_conversation_id

# 页面配置
st.set_page_config(
    page_title="网络开源威胁情报智能问答系统",
    page_icon="🛡️",
    layout="wide"
)

# ===================== 初始会话 =====================
init_session()

# ====================== 侧边栏 ======================
render_sidebar()

# ====================== 主区域 ======================
st.header("🛡️ 威胁情报智能问答")
st.caption("基于多智能体协作的网络开源威胁情报分析系统")

# -------- 输入区域（两列布局：文本输入 + 文件上传） --------
col1, col2 = st.columns([3, 1])

with col1:
    user_question = st.text_input(
        "请输入您的问题",
        placeholder="例如：APT29最近用了什么攻击手法？",
        label_visibility="collapsed",
        key="question_input"
    )

with col2:
    uploaded_file = st.file_uploader(
        "上传威胁报告",
        type=["txt", "docx", "pdf"],
        label_visibility="collapsed",
        key="file_uploader"
    )

# 提交按钮
submit_button = st.button("🔍 查询", type="primary", use_container_width=True)

# -------------------- 处理提交逻辑 --------------------
if submit_button:
    # 校验输入
    if not user_question and not uploaded_file:
        st.warning("⚠️ 请输入问题或上传威胁报告文件")
        st.stop()

    # 处理上传文件
    file_content = None
    if uploaded_file:
        with st.spinner("📄 正在解析文件..."):
            file_content = parse_file(uploaded_file.getvalue(), uploaded_file.type)
            if file_content:
                st.success(f"✅ 已解析文件：{uploaded_file.name}（{len(file_content)} 字符）")
            else:
                st.error("文件解析失败！")
                st.stop()

    # 调用后端api
    with st.spinner("🔄 正在分析威胁情报..."):
        try:
            conversation_id = get_conversation_id()
            response = query_backend(
                question=user_question if user_question else "请分析这份威胁报告",
                context=file_content,
                conversation_id=conversation_id
            )

            # 如果API不可用，使用Mock数据（开发阶段）
            if not response:
                st.warning("⚠️ 后端服务未启动，使用演示数据")
                response = get_mock_response(user_question or "威胁报告分析")

            # 保存响应到会话状态
            st.session_state.current_response = response

            # 保存会话ID
            if response and response.get("conversation_id"):
                set_conversation_id(response["conversation_id"])

            # 记录对话历史
            if user_question:
                add_message("user", user_question)
            elif uploaded_file:
                add_message("user", f"[上传文件] {uploaded_file.name}")

            if response and not response.get("refusal", False):
                add_message("assistant", response.get("answer", "无法生成回答"))
            elif response and response.get("refusal", False):
                add_message("assistant",
                            response.get("answer", f"[系统拒答] {response.get('refusal_reason', '无法回答该问题')}"))

        except Exception as e:
            st.error(f"❌ 请求失败: {str(e)}")
            st.stop()

# -------------------- 显示当前回答 --------------------
if st.session_state.get("current_response"):
    response = st.session_state.current_response

    # 检查是否拒答
    if response.get("refusal", False):
        st.warning(f"⚠️ {response.get('refusal_reason', '系统无法回答该问题')}")
        st.info("💡 建议您：\n- 换一种更具体的方式提问\n- 上传相关威胁报告文件后再次尝试")
    else:
        # ----- 回答正文 -----
        st.divider()
        st.markdown("### 📌 回答")
        st.markdown(response.get("answer", "暂无回答"))

        # ----- 置信度评分-----
        confidence = response.get("confidence", 0.0)
        st.markdown("### 📊 置信度评分")
        st.progress(confidence, text=f"{confidence:.1%}")

        # ----- 引用来源 -----
        citations = response.get("citations", [])
        if citations:
            st.markdown("### 📚 引用来源")
            for idx, citation in enumerate(citations, 1):
                with st.expander(f"来源{idx}: {citation.get('source', '未知来源')}"):
                    st.markdown(f">{citation.get('text', '无内容')}")
                    if citation.get("url"):
                        st.caption(f"🔗 [查看原文]({citation['url']})")

        # ----- IOC列表 -----
        entities = response.get("entities", {})
        iocs = {
            "ip": entities.get("ips", []) if isinstance(entities.get("ips"), list) else [],
            "domain": entities.get("domains", []) if isinstance(entities.get("domains"), list) else [],
            "hash": entities.get("hashes", []) if isinstance(entities.get("hashes"), list) else [],
            "cve": entities.get("cves", []) if isinstance(entities.get("cves"), list) else []
        }
        if any(iocs.values()):
            st.markdown("### 🔗 相关IOC")
            render_iocs(iocs)

        # ----- 威胁归因 -----
        attribution = response.get("attribution", {})
        verdict = attribution.get("verdict", "not_applicable")

        if verdict == "supported":
            actor = attribution.get("actor")
            rationale = attribution.get("rationale", "")
            support_ids = attribution.get("supporting_evidence_ids", [])

            st.markdown("### 👥 威胁组织归因")
            st.success(f"🕵️ 归因组织：**{actor}**")
            st.caption(f"📝 理由：{rationale}")
            if support_ids:
                st.caption(f"📎 支撑证据：{', '.join(support_ids)}")
            # 归因置信度
            st.caption(f"📊 归因可信度：{response.get('confidence', 0):.1%}")

        elif verdict == "inconclusive":
            actor = attribution.get("actor")
            rationale = attribution.get("rationale", "")

            st.markdown("### 👥 威胁组织归因")
            if actor:
                st.warning(f"⚠️ 可能涉及组织：**{actor}**（证据不充分）")
            else:
                st.warning("⚠️ 证据不足以确定威胁组织归属")
            st.caption(f"📝 说明：{rationale}")

        elif verdict == "not_applicable":
            # 问题不涉及归因，不显示任何内容
            pass

# -------------------- 评测结果 --------------------
with st.expander("📊 系统评测结果"):
    render_evaluation()

# -------------------- 多轮对话历史 --------------------
st.divider()
st.markdown("### 💬 对话历史")
render_chat_history()
