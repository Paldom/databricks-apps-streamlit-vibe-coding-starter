"""Shared utilities for Databricks Streamlit App."""
import hashlib
import os

import streamlit as st
from databricks import sql
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config

# Brand asset paths. Relative to the app's working directory at runtime,
# which on Databricks Apps and `uv run streamlit run` is the repo root.
_LOGO_LOCKUP = "assets/logos/lockup-primary-color.svg"
_LOGO_SYMBOL = "assets/logos/databricks-symbol-color.svg"


def get_env(name: str) -> str:
    """Get required env var or show an error and stop gracefully."""
    val = os.getenv(name)
    if not val:
        st.error(f"Missing environment variable: {name}")
        st.stop()
    return val


def get_user_token() -> str:
    """Get the user's OBO access token from Databricks Apps (headers)."""
    token = (st.context.headers or {}).get("X-Forwarded-Access-Token")
    if not token:
        st.error(
            "User token not available. Ensure this app is opened as a Databricks App "
            "and User authorization is enabled with scopes like 'sql' and 'dashboards.genie'."
        )
        st.stop()
    return token


def init_page(
    page_title: str,
    *,
    page_icon: str = _LOGO_SYMBOL,
    layout: str = "wide",
    initial_sidebar_state: str = "expanded",
) -> None:
    """Bootstrap a Streamlit page with Databricks branding.

    Call this as the very first Streamlit command of every page (entrypoint
    `app.py` and every file under `pages/`). It runs `st.set_page_config()`,
    registers the Databricks lockup/symbol via `st.logo()`, and renders the
    signed-in user badge in the sidebar — all in one place so pages cannot
    drift in look-and-feel.
    """
    st.set_page_config(
        page_title=page_title,
        page_icon=page_icon,
        layout=layout,
        initial_sidebar_state=initial_sidebar_state,
    )
    st.logo(
        _LOGO_LOCKUP,
        icon_image=_LOGO_SYMBOL,
        link="https://www.databricks.com",
    )
    _render_user_badge()


def _render_user_badge() -> None:
    """Render the signed-in user badge in the sidebar. Internal helper."""
    headers = st.context.headers or {}
    email = headers.get("X-Forwarded-Email")
    if not email:
        return
    md5 = hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest()
    avatar_url = f"https://www.gravatar.com/avatar/{md5}?s=64&d=identicon"
    with st.sidebar:
        st.markdown("#### Signed in")
        c1, c2 = st.columns([1, 3])
        with c1:
            st.image(avatar_url, width=64)
        with c2:
            st.caption(email)


def sql_conn():
    """Open a fresh DB-SQL connection per call, scoped to the signed-in user.

    Not cached: st.cache_resource is process-global and would leak one
    user's token to other sessions.
    """
    cfg = Config()
    warehouse_id = get_env("SQL_WAREHOUSE_ID")
    return sql.connect(
        server_hostname=cfg.host,
        http_path=f"/sql/1.0/warehouses/{warehouse_id}",
        access_token=get_user_token(),
    )


def workspace_client_app() -> WorkspaceClient:
    """WorkspaceClient using the Databricks App service principal (app authorization).

    Use this for APIs that handle OBO internally (e.g., the Genie Conversation API).
    """
    return WorkspaceClient()


def workspace_client_obo() -> WorkspaceClient:
    """WorkspaceClient using the signed-in user's forwarded token (user authorization)."""
    return WorkspaceClient(token=get_user_token(), auth_type="pat")
