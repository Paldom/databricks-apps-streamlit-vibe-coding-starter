"""NYC Taxi Genie (native) — chat UI over the Databricks Genie Conversation API.

Uses ``workspace_client_app()`` (the app's service principal, **not** OBO)
because the Conversation API handles OBO internally. The page renders a
native Streamlit chat — full theming control, sample-prompt buttons in the
sidebar, expandable SQL block, and the result set as an
``st.dataframe``. Compare with ``4_NYC_Taxi_Genie_iFrame.py`` (same Genie
Space, iframe embed) when you want to choose between native UX and the
workspace's own chat UI.

Session-state keys (namespaced so they don't collide with other pages):
- ``genie_messages``         : list[dict] — chat history (role, content, sql?, dataframe?)
- ``genie_conversation_id``  : str | None — Genie conversation handle
- ``_genie_prefill``         : str | None — quick-prompt staging slot
"""
import pandas as pd
import streamlit as st

from utils import get_env, init_page, workspace_client_app

init_page(page_title="NYC Taxi Genie (native)", page_icon=":material/smart_toy:")

SPACE_ID = get_env("GENIE_SPACE_ID")

st.title("NYC Taxi Genie — native")
st.caption(
    "Ask natural-language questions about `demo.nyctaxi.v_trips_genie` via "
    "the Databricks Genie Conversation API. Brand-consistent with the rest "
    "of the app — same fonts, colours, sidebar."
)

# --- Session state ----------------------------------------------------------
st.session_state.setdefault("genie_messages", [])
st.session_state.setdefault("genie_conversation_id", None)

# --- Sidebar: quick prompts + conversation control --------------------------
EXAMPLES = (
    "What are the top 10 pickup ZIP codes by valid trip count?",
    "How do trips and average fare vary by hour of day?",
    "Which routes have the highest average fare with at least 20 trips?",
    "What is the average fare on weekdays versus weekends?",
    "Show fare per mile by time of day.",
    "What are the top pickup ZIPs in the latest month in the dataset?",
)

with st.sidebar:
    st.divider()
    st.markdown("#### Example prompts")
    st.caption("Click to send:")
    for ex in EXAMPLES:
        if st.button(ex, use_container_width=True, key=f"genie_ex_{ex}"):
            st.session_state["_genie_prefill"] = ex
            st.rerun()

    st.divider()
    if st.session_state.genie_messages:
        if st.button("Clear conversation", use_container_width=True):
            st.session_state.genie_messages = []
            st.session_state.genie_conversation_id = None
            st.rerun()


# --- Render history (top-level — never nest chat_message contexts) ----------
for msg in st.session_state.genie_messages:
    with st.chat_message(msg["role"]):
        if msg.get("content"):
            st.markdown(msg["content"])
        if msg.get("sql"):
            with st.expander("SQL query"):
                st.code(msg["sql"], language="sql")
        df = msg.get("dataframe")
        if df is not None:
            st.dataframe(df, use_container_width=True, hide_index=True)


# --- Input: chat box + optional prefill from a sidebar button ---------------
prefill = st.session_state.pop("_genie_prefill", None)
user_prompt = st.chat_input("Ask a question about NYC taxi trips...")
prompt = prefill or user_prompt

if not prompt:
    st.stop()

# Echo user message
st.session_state.genie_messages.append({"role": "user", "content": prompt})
with st.chat_message("user"):
    st.markdown(prompt)


def _df_from_statement(w, statement_id: str) -> pd.DataFrame | None:
    """Fetch a Genie-generated query result as a pandas DataFrame."""
    if not statement_id:
        return None
    stmt = w.statement_execution.get_statement(statement_id)
    if not (stmt.result and stmt.result.data_array):
        return None
    columns = [col.name for col in stmt.manifest.schema.columns]
    return pd.DataFrame(stmt.result.data_array, columns=columns)


with st.chat_message("assistant"):
    with st.spinner("Thinking..."):
        try:
            w = workspace_client_app()

            if st.session_state.genie_conversation_id is None:
                result = w.genie.start_conversation_and_wait(
                    space_id=SPACE_ID,
                    content=prompt,
                )
                st.session_state.genie_conversation_id = result.conversation_id
            else:
                result = w.genie.create_message_and_wait(
                    space_id=SPACE_ID,
                    conversation_id=st.session_state.genie_conversation_id,
                    content=prompt,
                )

            response_text_parts: list[str] = []
            response_sql: str | None = None

            for att in result.attachments or []:
                if att.text and att.text.content:
                    response_text_parts.append(att.text.content)
                if att.query and att.query.query:
                    response_sql = att.query.query

            response_df = None
            if getattr(result, "query_result", None):
                response_df = _df_from_statement(w, result.query_result.statement_id)

            response_text = "\n\n".join(response_text_parts).strip() or "Done."

            # Render the assistant turn inline ...
            st.markdown(response_text)
            if response_sql:
                with st.expander("SQL query"):
                    st.code(response_sql, language="sql")
            if response_df is not None:
                st.dataframe(response_df, use_container_width=True, hide_index=True)

            # ... and persist it so it survives the next rerun.
            saved: dict = {"role": "assistant", "content": response_text}
            if response_sql:
                saved["sql"] = response_sql
            if response_df is not None:
                saved["dataframe"] = response_df
            st.session_state.genie_messages.append(saved)

        except Exception as exc:
            error_text = f"Error talking to Genie: {exc}"
            st.error(error_text)
            st.session_state.genie_messages.append(
                {"role": "assistant", "content": error_text}
            )
