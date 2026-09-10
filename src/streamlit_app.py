"""
Streamlit interface for CTM/ETM energy data pipeline.
Handles DSH data processing and CTM session management.
"""

import streamlit as st
from pathlib import Path
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent
sys.path.insert(0, str(src_path))

from ui.streamlit_utils import *
from ui.tab_dsh_input import render_dsh_input_tab
from ui.tab_ctm_workflow import render_ctm_workflow_tab
from ui.tab_visualization import render_visualization_tab
from ui.tab_regionalization import render_regionalization_tab
from ui.sidebar_credentials import render_credentials_sidebar, show_memory_usage
from ui.sidebar_downloads import render_sidebar_downloads



# ── Page config ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DSH-CTM-ETM Pipeline",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

show_memory_usage()
render_credentials_sidebar()

# ── Main tabs ──────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["DSH Input & Output", "CTM/ETM Workflow", "Visualization", 'Regionalization'])

with tab1:
    render_dsh_input_tab()

with tab2:
    render_ctm_workflow_tab()

with tab3:
    render_visualization_tab()
with tab4:
    render_regionalization_tab()

render_sidebar_downloads()

# ── Footer ─────────────────────────────────────────────────────────────
st.divider()
st.caption("DSH-CTM-ETM Pipeline | v1.0")