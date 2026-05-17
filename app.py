"""Databricks Streamlit App - Main Entrypoint."""
import streamlit as st
from utils import render_sidebar

# Configure page title and icon
st.set_page_config(
    page_title="Databricks Streamlit Starter",
    page_icon="🏭",
    layout="wide"
)

# Render sidebar with logo and user badge
render_sidebar()

# Main page content
st.title("🏭 Databricks Analytics")

st.markdown("""
Welcome to the Databricks Streamlit starter. This template is wired for
on-behalf-of (OBO) authentication, so any queries you add will respect
Unity Catalog row and column policies.

To get started, add pages under the `pages/` directory. The included
`pages/0_empty.py` is a template showing how to use the shared helpers in
`utils.py` (env vars, SQL connections, workspace clients). Common patterns
you can build on top of this starter:

- Unity Catalog table viewer
- Genie AI chat interface
- Embedded AI/BI dashboard
- Custom data visualizations
- Interactive data editing
""")

st.info("👈 Open the **Empty** template page from the sidebar, or add your own under `pages/`.")
