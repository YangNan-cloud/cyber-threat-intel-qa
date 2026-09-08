import streamlit as st


def render_iocs(iocs: dict):
    """渲染IOC列表，按类别分列展示"""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown("**🟣 IP地址**")
        for item in iocs.get("ip", []):
            st.code(item, language="text")
        if not iocs.get("ip"):
            st.caption("无")

    with col2:
        st.markdown("**🟢 域名**")
        for item in iocs.get("domain", []):
            st.code(item, language="text")
        if not iocs.get("domain"):
            st.caption("无")

    with col3:
        st.markdown("**🔴 文件哈希**")
        for item in iocs.get("hash", []):
            # 截断显示
            display = item[:16] + "..." if len(item) > 16 else item
            st.code(display, language="text")
        if not iocs.get("hash"):
            st.caption("无")

    with col4:
        st.markdown("**🟡 CVE编号**")
        for item in iocs.get("cve", []):
            st.code(item, language="text")
        if not iocs.get("cve"):
            st.caption("无")