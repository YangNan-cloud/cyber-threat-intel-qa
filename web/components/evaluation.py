import streamlit as st


def render_evaluation():
    """渲染评测结果"""
    # 这里先用占位数据
    metrics = st.session_state.get("evaluation_metrics", {
        "em": 0.72,
        "f1": 0.68,
        "recall_at_10": 0.85,
        "mrr": 0.79,
        "retrieval_precision": 0.76,
        "attribution_accuracy": 0.81
    })

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("EM (精确匹配)", f"{metrics.get('em', 0):.1%}")
    with col2:
        st.metric("F1 (问答)", f"{metrics.get('f1', 0):.1%}")
    with col3:
        st.metric("Recall@10", f"{metrics.get('recall_at_10', 0):.1%}")
    with col4:
        st.metric("MRR", f"{metrics.get('mrr', 0):.1%}")

    with st.expander("📈 详细评测指标"):
        st.json(metrics)
