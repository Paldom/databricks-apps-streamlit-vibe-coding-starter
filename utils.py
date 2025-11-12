"""Shared utilities for Databricks Streamlit App."""
import os
import hashlib
import streamlit as st
from databricks import sql
from databricks.sdk.core import Config
from databricks.sdk import WorkspaceClient


def get_env(name: str) -> str:
    """Get required env var or show an error and stop gracefully."""
    val = os.getenv(name)
    if not val:
        st.error(f"Missing environment variable: {name}")
        st.stop()
    return val


def get_user_token() -> str:
    """Get the user's OBO access token from Databricks Apps (headers)."""
    # Requires User authorization to be enabled with the right scopes (e.g., sql, dashboards.genie).
    token = (st.context.headers or {}).get("X-Forwarded-Access-Token")
    if not token:
        st.error(
            "User token not available. Ensure this app is opened as a Databricks App "
            "and User authorization is enabled with scopes like 'sql' and 'dashboards.genie'."
        )
        st.stop()
    return token


def render_sidebar():
    """Render sidebar with logo and user badge."""
    st.logo("assets/logo.svg")

    headers = st.context.headers or {}
    email = headers.get("X-Forwarded-Email")

    avatar_url = None
    if email:
        md5 = hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest()
        avatar_url = f"https://www.gravatar.com/avatar/{md5}?s=64&d=identicon"

    with st.sidebar:
        st.markdown("#### Signed in")
        c1, c2 = st.columns([1, 3])
        with c1:
            if avatar_url:
                st.image(avatar_url, width=64)
        with c2:
            if email:
                st.caption(email)


@st.cache_resource
def sql_conn():
    """Cache a DB SQL connection that uses the current user's token (OBO)."""
    cfg = Config()  # host comes from Databricks Apps env (DATABRICKS_HOST) when running in Apps
    warehouse_id = get_env("SQL_WAREHOUSE_ID")
    http_path = f"/sql/1.0/warehouses/{warehouse_id}"
    return sql.connect(
        server_hostname=cfg.host,
        http_path=http_path,
        credentials_provider=lambda: cfg.authenticate
    )

def workspace_client():
    """WorkspaceClient that runs with the current user (OBO)."""
    return WorkspaceClient()


def workspace_client_obo():
    """WorkspaceClient that runs with the current user (OBO)."""
    return WorkspaceClient(token=get_user_token(), auth_type="pat")

