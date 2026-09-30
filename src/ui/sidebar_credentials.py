"""Sidebar: ETM token (cached in session_state) and memory usage metric."""

import streamlit as st
import psutil
import gc


def show_memory_usage():
    process = psutil.Process()
    mem_mb = process.memory_info().rss / 1024 / 1024
    st.sidebar.metric("Memory Usage", f"{mem_mb:.0f} MB")
    if st.sidebar.button("Clear Cache", use_container_width=True):
        clear_session_cache()
        st.success("Cache cleared")


def clear_session_cache():
    """Clear all session state."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    gc.collect()


def render_credentials_sidebar():
    """Renders the ETM token input. Call once, near the top of the app."""
    if "etm_token" not in st.session_state:
        st.session_state.etm_token = ""

    st.sidebar.markdown("### Credentials (Cached)")

    with st.sidebar.expander("ETM Settings", expanded=False):
        etm_token = st.text_input(
            "ETM Authorization Token",
            value=st.session_state.etm_token,
            type="password",  
            key="etm_token_input",
        )
        if etm_token:
            st.session_state.etm_token = etm_token
            st.success("Token cached")
