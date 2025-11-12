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
Welcome to the Databricks Analytics platform. Use the sidebar to navigate between pages:

- **Unity Catalog** - View and query Unity Catalog tables with user-level permissions
- **Chat with Genie** - Ask questions about your data using AI
- **Dashboard** - View embedded AI/BI dashboards

All queries run with on-behalf-of (OBO) authentication, respecting Unity Catalog row and column policies.
""")

st.info("👈 Select a page from the sidebar to get started")
