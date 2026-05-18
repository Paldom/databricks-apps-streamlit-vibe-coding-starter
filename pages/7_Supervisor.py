"""Supervisor Agent — chat over a Supervisor that routes to Genie + KA.

The Supervisor's serving endpoint returns an OpenAI Responses-shaped
payload whose ``output[]`` is a multi-turn TRACE, not a single answer:

    1. supervisor "planning" text       e.g. "I'll query the NYC taxi data..."
    2. boundary marker                  "<name>nyc_taxi_genie</name>"
    3. subagent tool output             (Genie table / KA prose + citations)
    4. boundary marker                  "<name>enterprise-supervisor-agent</name>"
    5. supervisor synthesis             the final user-facing answer

This page parses the trace into labelled sections, surfaces the final
synthesis at the top, and tucks the intermediate steps into an
expandable "Reasoning + tool calls" panel — so users see a clean answer
by default but can audit which subagent contributed which fact.

Auth: ``workspace_client_app()`` — the App service principal. The SP
needs ``CAN_QUERY`` on the supervisor endpoint AND on every subagent
endpoint the supervisor may delegate to (KA endpoint + Genie Space).
Without all three, the supervisor returns a partial / 403 response.
"""
import re

import requests
import streamlit as st

from utils import get_env, init_page, workspace_client_app

init_page(page_title="Supervisor Agent", page_icon=":material/hub:")

ENDPOINT_NAME = get_env("SUPERVISOR_ENDPOINT_NAME")
SUPERVISOR_NAME = "enterprise-supervisor-agent"  # matches `name=` from manage_mas

st.title("Supervisor Agent")
st.caption(
    "Single chat over both the **NYC Taxi Genie** (structured analytics) and "
    "the **Northwind Knowledge Assistant** (policy docs). The supervisor "
    "picks the right specialist — or both — per question."
)

# --- Session state ----------------------------------------------------------
st.session_state.setdefault("supervisor_messages", [])

# --- Sidebar: routing-test quick prompts + controls -------------------------
# Each example deliberately exercises a different routing path: pure Genie,
# pure KA, an out-of-scope refusal, and two mixed-domain prompts that should
# fan out to both subagents and synthesise.
EXAMPLES = (
    "What are the top 5 pickup ZIP codes by valid trip count?",           # Genie
    "How many PTO days does an employee with 4 years of tenure accrue?",  # KA
    "What is Northwind's 401(k) employer match percentage?",              # KA refusal
    "What is the average fare per mile by time of day, and what does our travel policy say about per-diem?",  # mixed
    "Which pickup-dropoff routes have the highest average fare, and does the sustainability report mention transport emissions?",  # mixed
)

with st.sidebar:
    st.divider()
    st.markdown("#### Example prompts")
    st.caption("Designed to exercise routing:")
    for ex in EXAMPLES:
        if st.button(ex, use_container_width=True, key=f"sup_ex_{ex}"):
            st.session_state["_supervisor_prefill"] = ex
            st.rerun()

    st.divider()
    if st.session_state.supervisor_messages:
        if st.button("Clear conversation", use_container_width=True):
            st.session_state.supervisor_messages = []
            st.rerun()


# --- Render history (top-level — never nest chat_message contexts) ----------
for msg in st.session_state.supervisor_messages:
    with st.chat_message(msg["role"]):
        if msg.get("content"):
            st.markdown(msg["content"])
        if msg.get("trace"):
            with st.expander("Reasoning + tool calls"):
                for speaker, text in msg["trace"]:
                    st.markdown(f"**{speaker}**")
                    st.markdown(text)
                    st.markdown("---")


# --- Input: chat box + optional prefill from a sidebar button ---------------
prefill = st.session_state.pop("_supervisor_prefill", None)
user_prompt = st.chat_input("Ask anything about taxi data, Northwind policies, or both...")
prompt = prefill or user_prompt

if not prompt:
    st.stop()

st.session_state.supervisor_messages.append({"role": "user", "content": prompt})
with st.chat_message("user"):
    st.markdown(prompt)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NAME_RE = re.compile(r"^\s*<name>(?P<name>.+?)</name>\s*$")


def _parse_trace(response: dict) -> list[tuple[str, str]]:
    """Split the supervisor response into ordered (speaker, text) sections.

    The supervisor encodes turn boundaries by emitting bare
    ``<name>...</name>`` text blocks; everything after a marker (until the
    next marker) belongs to that speaker. The very first speaker is the
    supervisor itself.
    """
    sections: list[tuple[str, str]] = []
    current_speaker = SUPERVISOR_NAME
    current_chunks: list[str] = []

    def flush() -> None:
        if current_chunks:
            sections.append((current_speaker, "\n".join(current_chunks).strip()))

    for msg in response.get("output") or []:
        for part in msg.get("content") or []:
            if part.get("type") != "output_text":
                continue
            text = part.get("text") or ""
            m = _NAME_RE.match(text)
            if m:
                flush()
                current_chunks = []
                current_speaker = m.group("name").strip()
            else:
                if text.strip():
                    current_chunks.append(text)

    flush()
    return [(s, t) for s, t in sections if t]


def _final_answer(sections: list[tuple[str, str]]) -> tuple[str, list[tuple[str, str]]]:
    """Return (final_supervisor_synthesis, reasoning_trace)."""
    if not sections:
        return ("(no answer returned)", [])
    # Walk backwards to find the most recent supervisor block — that's
    # the final synthesis after the last tool call.
    for i in range(len(sections) - 1, -1, -1):
        if sections[i][0] == SUPERVISOR_NAME:
            final = sections[i][1]
            trace = sections[:i] + sections[i + 1 :]
            return (final, trace)
    # No supervisor turn — fall back to the last section overall.
    return (sections[-1][1], sections[:-1])


def _query_supervisor(endpoint_name: str, prompt: str) -> dict:
    """POST a single user turn and return the parsed JSON."""
    w = workspace_client_app()
    headers = w.config.authenticate()
    resp = requests.post(
        f"{w.config.host}/serving-endpoints/{endpoint_name}/invocations",
        headers=headers,
        json={"input": [{"role": "user", "content": prompt}]},
        timeout=180,    # supervisor may chain multiple tool calls
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Run the supervisor and render
# ---------------------------------------------------------------------------

with st.chat_message("assistant"):
    with st.spinner("Routing through specialists..."):
        try:
            response = _query_supervisor(ENDPOINT_NAME, prompt)
            sections = _parse_trace(response)
            answer, trace = _final_answer(sections)

            st.markdown(answer)

            if trace:
                with st.expander(
                    f"Reasoning + tool calls ({len(trace)} step"
                    + ("s" if len(trace) != 1 else "")
                    + ")",
                ):
                    for speaker, text in trace:
                        st.markdown(f"**{speaker}**")
                        st.markdown(text)
                        st.markdown("---")

            saved: dict = {"role": "assistant", "content": answer}
            if trace:
                saved["trace"] = trace
            st.session_state.supervisor_messages.append(saved)

        except Exception as exc:
            err = f"Error talking to the Supervisor Agent: {exc}"
            st.error(err)
            st.session_state.supervisor_messages.append(
                {"role": "assistant", "content": err}
            )
