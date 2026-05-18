"""Knowledge Assistant — chat over the Northwind Robotics PDFs.

Talks to a Databricks Agent Bricks "Knowledge Assistant" serving endpoint
(OpenAI Responses-shaped API). The endpoint name comes from ``app.yaml``
as ``KA_ENDPOINT_NAME``; the App service principal needs ``CAN_QUERY`` on
that endpoint (the only permission required — the endpoint owns its own
UC access to the source volume).

Session-state keys (namespaced to avoid colliding with other chat pages):
- ``ka_messages``   : list[dict] — chat history with optional citations.
- ``_ka_prefill``   : str | None — quick-prompt staging slot.
"""
import requests
import streamlit as st

from utils import get_env, init_page, workspace_client_app

init_page(page_title="Knowledge Assistant", page_icon=":material/menu_book:")

ENDPOINT_NAME = get_env("KA_ENDPOINT_NAME")

st.title("Knowledge Assistant — Northwind")
st.caption(
    "Ask questions about the Employee Handbook, Travel & Expense Policy, "
    "and 2024 Sustainability Report. Answers come from "
    "`/Volumes/demo/knowledge_assistant/docs` via Databricks Agent Bricks "
    "and always cite their source."
)

# --- Session state ----------------------------------------------------------
st.session_state.setdefault("ka_messages", [])

# --- Sidebar: quick prompts + conversation control --------------------------
# Drawn from the project's RAG eval set (single-hop facts, multi-hop / cross-doc,
# and one deliberately out-of-scope question to exercise the refusal path).
EXAMPLES = (
    "How many PTO days does an employee with 4 years of tenure accrue per year?",
    "What is the receipt threshold for reimbursable expenses?",
    "What class of travel is permitted for a 6-hour flight?",
    "By how much did Scope 2 emissions change from 2023 to 2024?",
    "If the Employee Handbook and the Travel & Expense Policy disagree on an expense matter, which one wins?",
    "What is Northwind's 401(k) employer match percentage?",  # out of scope → should refuse
)

with st.sidebar:
    st.divider()
    st.markdown("#### Example prompts")
    st.caption("Click to send:")
    for ex in EXAMPLES:
        if st.button(ex, use_container_width=True, key=f"ka_ex_{ex}"):
            st.session_state["_ka_prefill"] = ex
            st.rerun()

    st.divider()
    if st.session_state.ka_messages:
        if st.button("Clear conversation", use_container_width=True):
            st.session_state.ka_messages = []
            st.rerun()


# --- Render history (top-level — never nest chat_message contexts) ----------
for msg in st.session_state.ka_messages:
    with st.chat_message(msg["role"]):
        if msg.get("content"):
            st.markdown(msg["content"])
        if msg.get("citations"):
            with st.expander(f"Citations ({len(msg['citations'])})"):
                for c in msg["citations"]:
                    st.markdown(f"- {c}")


# --- Input: chat box + optional prefill from a sidebar button ---------------
prefill = st.session_state.pop("_ka_prefill", None)
user_prompt = st.chat_input("Ask a question about Northwind...")
prompt = prefill or user_prompt

if not prompt:
    st.stop()

st.session_state.ka_messages.append({"role": "user", "content": prompt})
with st.chat_message("user"):
    st.markdown(prompt)


def _format_citations(annotations) -> list[str]:
    """Turn Responses-API annotations into readable markdown bullets.

    Knowledge Assistant emits OpenAI-style annotations; we handle the two
    most common shapes (`file_citation`, `url_citation`) and fall back to
    a string preview for anything new.
    """
    out: list[str] = []
    for ann in annotations or []:
        if not isinstance(ann, dict):
            out.append(f"`{str(ann)[:200]}`")
            continue
        atype = ann.get("type")
        if atype == "file_citation":
            fname = ann.get("filename") or ann.get("file_id") or "(unknown file)"
            out.append(f"📄 `{fname}`")
        elif atype == "url_citation":
            title = ann.get("title") or ann.get("url") or "(link)"
            url = ann.get("url") or "#"
            out.append(f"🔗 [{title}]({url})")
        else:
            out.append(f"`{str(ann)[:200]}`")
    return out


def _query_ka(endpoint_name: str, prompt: str) -> dict:
    """POST a single user turn to the KA endpoint and return the parsed JSON.

    Uses the workspace client to mint the OAuth token; sends the
    OpenAI Responses-shaped body. (`messages` is rejected by the KA
    endpoint — it requires `input`.)
    """
    w = workspace_client_app()
    headers = w.config.authenticate()
    url = f"{w.config.host}/serving-endpoints/{endpoint_name}/invocations"
    resp = requests.post(
        url,
        headers=headers,
        json={"input": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


with st.chat_message("assistant"):
    with st.spinner("Searching the knowledge base..."):
        try:
            response = _query_ka(ENDPOINT_NAME, prompt)

            # OpenAI Responses-API shape:
            #   response["output"] = [{"role": "assistant", "content": [{"type": "output_text",
            #                                                            "text": "...",
            #                                                            "annotations": [...]}]}]
            answer_parts: list[str] = []
            citations: list[str] = []
            for msg in response.get("output") or []:
                if msg.get("role") != "assistant":
                    continue
                for part in msg.get("content") or []:
                    if part.get("type") == "output_text":
                        if part.get("text"):
                            answer_parts.append(part["text"])
                        citations.extend(_format_citations(part.get("annotations")))

            answer = "\n\n".join(answer_parts).strip() or "(no answer returned)"
            sources_used = bool((response.get("custom_outputs") or {}).get("sources_used"))

            st.markdown(answer)

            if citations:
                with st.expander(f"Citations ({len(citations)})", expanded=True):
                    for c in citations:
                        st.markdown(f"- {c}")
            elif not sources_used:
                st.info(
                    "The assistant didn't use any knowledge sources for this "
                    "answer. If the question is in-scope, the source ingestion "
                    "may still be in progress — check the Knowledge Source "
                    "state in the workspace (Agents → Northwind Knowledge "
                    "Assistant → sources)."
                )

            saved = {"role": "assistant", "content": answer}
            if citations:
                saved["citations"] = citations
            st.session_state.ka_messages.append(saved)

        except Exception as exc:
            err = f"Error talking to the Knowledge Assistant: {exc}"
            st.error(err)
            st.session_state.ka_messages.append(
                {"role": "assistant", "content": err}
            )
