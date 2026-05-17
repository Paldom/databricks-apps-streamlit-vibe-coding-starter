"""Databricks Streamlit App - Main Entrypoint."""
import streamlit as st

from utils import init_page

init_page(page_title="Databricks Streamlit Starter")

st.title("Databricks Analytics")

st.markdown(
    """
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
- Custom data visualisations
- Interactive data editing

Visual style follows the Databricks Design System — see
[`DESIGN-SYSTEM.md`](DESIGN-SYSTEM.md).
"""
)

st.info("Open the **Empty** template page from the sidebar, or add your own under `pages/`.")
