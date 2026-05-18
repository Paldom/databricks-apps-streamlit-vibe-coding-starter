# Implementation Plan — Supervisor Agent Page (Genie + Knowledge Assistant)

Page-specific plan for `pages/7_Supervisor.py` — a single chat UI over a Databricks Agent Bricks **Multi-Agent Supervisor (MAS)** that routes between two specialist subagents: the NYC Taxi Genie Space (structured analytics) and the Northwind Knowledge Assistant (document Q&A). For mixed-domain questions the supervisor fans out to both subagents and synthesises one answer. The Streamlit page is thin — chat UI + trace parsing + final-answer rendering with an expandable reasoning panel.

> **Prerequisites.**
> - **`0_A_initial_setup.md`** must be done — App, `databricks.yml`, `utils.py`, `app.py`, `app.yaml`, `pyproject.toml`, `uv.lock` already in place; worksheet §1.1 values (`app_name`, `user_group_app`, …) captured.
> - **`0_D_genie_setup.md`** is **required** — the supervisor's `nyc_taxi_genie` subagent reads from the Genie Space created there. The App SP must hold `CAN_RUN` on that space + UC `SELECT` on the source view (also covered by 0_D §3.4 + §3.3 of the related `1_E` native chat plan).
> - **`1_F_knowledge_assistant_page.md`** is **required** — the supervisor's `northwind_knowledge_assistant` subagent calls the KA serving endpoint created there. The App SP must hold `CAN_QUERY` on `ka-<hash>-endpoint` (covered by 1_F §3.5).

> **Top gotchas (from the implementation).**
> 1. The supervisor endpoint's response body **is not a single answer** — `output[]` is a multi-turn trace where each `<name>subagent</name>` text block marks a speaker boundary. Picking the right "final" section requires walking the trace; rendering the raw concatenation looks confusing.
> 2. The App SP needs `CAN_QUERY` on **three** endpoints (or equivalent): the supervisor, the KA endpoint, and the Genie Space ACL. Missing any one of the three turns a fan-out question into a partial / 403 answer.
> 3. The Multi-Agent Supervisor REST endpoint uses the **OpenAI Responses-API shape** (`{"input": [...]}`), the same as the KA endpoint. **`messages` is rejected.**
> 4. The `manage_mas` MCP tool returns `endpoint_status: NOT_APPLICABLE` and no endpoint name. Capture the endpoint name from `databricks supervisor-agents list-supervisor-agents`.
> 5. Permissions PATCH path needs the **endpoint ID**, not the name. Look up via `databricks serving-endpoints get <name>`.

---

## 1. Parameters to set

Page-specific knobs; app-level values are reused from `0_A_initial_setup.md` §1.1.

| Parameter | Where it lives | Notes |
|---|---|---|
| Supervisor display name | `manage_mas(name=…)` / CLI positional | Free-form; unique at workspace level. |
| Supervisor description | `manage_mas(description=…)` | One-line user-facing summary. |
| Supervisor instructions | `manage_mas(instructions=…)` | The system prompt that controls routing + synthesis. Critical — see §3.2 for the production-ready text. |
| Subagent references | `manage_mas(agents=[…])` | Each item carries a `name`, a `description` (**critical for routing — supervisor delegates by matching question against descriptions**), and exactly ONE of `endpoint_name` / `genie_space_id` / `ka_tile_id` / `uc_function_name` / `connection_name`. |
| SME examples | `manage_mas(examples=[…])` | List of `{question, guideline}` pairs that train the routing behaviour. Improves quality more than tweaking instructions alone. |
| Supervisor tile ID | Returned by `manage_mas(create_or_update)` | The Agent Bricks identifier. Cache for future `update` / `delete`. |
| Supervisor endpoint name | `databricks supervisor-agents list-supervisor-agents` | Pattern: `mas-<short-hash>-endpoint`. Goes into `app.yaml` as the literal `value:`. |
| Supervisor endpoint ID | `databricks serving-endpoints get <name>` → `.id` | Needed for the permissions PATCH. **The name does not work** in `/api/2.0/permissions/serving-endpoints/<X>`. |
| App SP client ID | `databricks apps get <app_name> -o json` → `.service_principal_client_id` | The identity that calls the supervisor at runtime. Must hold `CAN_QUERY` on supervisor, `CAN_QUERY` on KA, and `CAN_RUN` on the Genie Space. |
| Example prompts | In-code `EXAMPLES` tuple in the page | Five sidebar quick-prompts that deliberately exercise different routing paths. |
| Page title / icon / filename | `init_page(...)` + filename | Streamlit-rendered. |

### 1.1 Fill-in worksheet

- **`SUPERVISOR_DISPLAY_NAME`** = `enterprise-supervisor-agent`
- **`SUPERVISOR_TILE_ID`** (captured after create) = `__________________`
- **`SUPERVISOR_ENDPOINT_NAME`** (captured after create — goes in `app.yaml`) = `__________________`
- **`SUPERVISOR_ENDPOINT_ID`** (lookup after deploy; needed for the permissions PATCH) = `__________________`
- **`GENIE_SPACE_ID`** (inherited from `0_D_genie_setup.md` §1.1) = `__________________`
- **`KA_TILE_ID`** (inherited from `1_F_knowledge_assistant_page.md` §1.1) = `__________________`
- **`app_sp_client_id`** (from `databricks apps get <app_name> -o json`) = `__________________`
- **`subagent_genie_name`** = `nyc_taxi_genie`
- **`subagent_ka_name`** = `northwind_knowledge_assistant`
- **Page title** = `Supervisor Agent`
- **Page icon** = `:material/hub:`
- **Page filename** = `pages/7_Supervisor.py`

---

## 2. Overview

**What the page does.**

1. Reads `SUPERVISOR_ENDPOINT_NAME` from `app.yaml`.
2. Renders prior chat turns from `st.session_state.supervisor_messages` — each historical turn keeps both the final synthesis (`content`) and the reasoning trace (`trace`).
3. On a new prompt (typed or via a sidebar quick-prompt), POSTs to `/serving-endpoints/<supervisor-endpoint>/invocations` with `{"input": [{"role": "user", "content": prompt}]}` and the App SP's OAuth token.
4. Parses the supervisor's multi-turn `output[]` into ordered `(speaker, text)` sections using the `<name>...</name>` boundary markers.
5. Extracts the **final supervisor synthesis** (the last section whose speaker is the supervisor) and renders it as the assistant chat bubble; everything else (supervisor planning, each subagent's raw output) goes into an expandable *"Reasoning + tool calls (N steps)"* panel.
6. Persists both the synthesis and the trace into session state.

**Why a supervisor, not direct routing in app code.** The supervisor is a managed Agent Bricks artefact: routing rules, SME examples, and synthesis prompts live with the agent in the workspace (auditable, tunable, governable) rather than scattered across Streamlit code. You can rev routing without redeploying the app. Adding a third or fourth subagent later is a workspace-side change, not a code change.

**Why fan-out for mixed questions matters.** The supervisor's instructions tell it to call BOTH subagents for cross-domain prompts (e.g. *"highest-fare routes AND what the sustainability report says about transport"*) and synthesise an answer with H3-headed sections per subagent. Without a supervisor, this would require app-side orchestration code (call Genie, call KA, prompt an LLM to merge — 100+ lines of glue and another model dependency).

**Why parse the trace into sections instead of rendering raw.** The supervisor response body is a multi-turn TRACE:

```
output[0]: assistant — "I'll query the NYC taxi data..."          ← supervisor planning
output[1]: assistant — "<name>nyc_taxi_genie</name>"              ← speaker boundary
output[2]: assistant — "<table of top ZIPs>"                      ← Genie tool output
output[3]: assistant — "<name>enterprise-supervisor-agent</name>" ← speaker boundary
output[4]: assistant — "The top 5 pickup ZIP codes are..."        ← final synthesis
```

Concatenating all of that into a single chat bubble shows the user the raw `<name>…</name>` markers and Genie's intermediate table — confusing. Picking only the final supervisor block gives a clean answer; the rest goes into an expander for users who want to audit which subagent produced each fact.

**Why App SP auth (and the OBO trade-off).** Same pattern as the KA + native-Genie pages: `workspace_client_app()` uses the App's service principal. The SP needs three explicit grants (supervisor `CAN_QUERY`, KA `CAN_QUERY`, Genie `CAN_RUN`) which we already provisioned in earlier plans. The trade-off vs. OBO: every viewer shares the same effective permissions inside the supervisor. For production, switch to OBO by adding `user_api_scopes: [serving.serving-endpoints, dashboards.genie, sql]` to the bundle's app config, swapping `workspace_client_app()` for `workspace_client_obo()`, and granting the user group (not the SP) on every subagent — but that's a separate hardening pass.

**End-to-end flow.**

```
existing Genie Space (from 0_D)   existing KA endpoint (from 1_F)
        │                                 │
        └───────────┬─────────────────────┘
                    ▼
        manage_mas(create_or_update, agents=[<genie>, <ka>], instructions=…, examples=…)
                    │
                    ▼
        Supervisor tile + serving endpoint   ← SUPERVISOR_ENDPOINT_NAME captured
                    │
                    │ databricks api patch /api/2.0/permissions/serving-endpoints/<ID>
                    │   App SP → CAN_QUERY
                    ▼
        app.yaml SUPERVISOR_ENDPOINT_NAME = "mas-<hash>-endpoint"
                    │
                    ▼
        init_page() + chat UI (st.chat_message / st.chat_input + sidebar prompts)
                    │
                    ▼
        POST /serving-endpoints/<name>/invocations
            body: {"input": [{"role": "user", "content": prompt}]}
            headers: w.config.authenticate()         ← App SP OAuth
                    │
                    ▼
        Response (multi-turn trace):
            output[] with interleaved <name>…</name> markers
                    │
                    ▼  _parse_trace() + _final_answer()
        final supervisor synthesis (rendered top)
        reasoning trace          (rendered in expander)
```

**Failure modes the page handles.**

- Missing `SUPERVISOR_ENDPOINT_NAME` env var → friendly `st.error(...)` via `get_env()` then `st.stop()`.
- Endpoint 4xx / 5xx (auth or supervisor down) → caught and persisted as an assistant chat turn so the user keeps prior context.
- Trace with no supervisor synthesis section → `_final_answer()` falls back to the last section overall.
- Empty `output[]` → falls back to *"(no answer returned)"* and an empty trace.
- Partial fan-out (supervisor reached one subagent but the other 403'd) → the synthesis text will say so; the trace expander shows which subagent succeeded.

---

## 3. Databricks-side prerequisites and setup

§3.1–§3.5 are the concrete steps. §3.6 is a Claude Code prompt that drives them idempotently. §3.7 is the deploy / smoke loop.

### 3.1 Required resources

- Genie Space + Knowledge Assistant from `0_D_genie_setup.md` + `1_F_knowledge_assistant_page.md`. Both already published and answering.
- App SP already holds **`CAN_RUN`** on the Genie Space + UC `SELECT`/`USE_CATALOG`/`USE_SCHEMA` along the source-view path (from `0_D` §3.4 / `1_E` §3.2-§3.3).
- App SP already holds **`CAN_QUERY`** on the KA endpoint (from `1_F` §3.5).

Without all three pre-conditions the supervisor will partially fail. Re-verify with:

```bash
APP_SP="<app_sp_client_id from databricks apps get>"

# Genie Space ACL — SP should appear with CAN_RUN
databricks api get /api/2.0/permissions/genie/<GENIE_SPACE_ID>

# KA endpoint ACL — SP should appear with CAN_QUERY
KA_EP_ID=$(databricks serving-endpoints get <KA_ENDPOINT_NAME> -o json | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')
databricks api get /api/2.0/permissions/serving-endpoints/$KA_EP_ID
```

### 3.2 Create the supervisor

The supervisor wires together the Genie Space and the KA, plus the routing instructions and SME examples. Both subagents are referenced by their existing identifiers — **not duplicated**. Use the MCP `manage_mas` tool (cleanest) or the equivalent CLI.

#### Via MCP (preferred — single call)

```text
manage_mas(
  action            = "create_or_update",
  name              = "enterprise-supervisor-agent",
  description       = "Routes user questions to the right specialist: NYC Taxi Genie for structured trip analytics, or Northwind Knowledge Assistant for policy / handbook / sustainability questions.",
  agents = [
    {
      "name":            "nyc_taxi_genie",
      "description":     "Use this Genie Space for STRUCTURED ANALYTICS over the NYC taxi trips dataset. Trip counts, fares (fare_amount_usd; metered only — NO tips/tolls/total), distances in miles, durations in minutes, pickup/dropoff ZIPs, OD routes, hour-of-day, day-of-week, time-of-day buckets. Date range Jan 1 - Feb 29, 2016 only. Use for counts/sums/avgs/rankings/top-N/trends/KPIs over taxi rides. Do NOT use for HR policy, expense rules, sustainability, or any Northwind topic.",
      "genie_space_id":  "<GENIE_SPACE_ID>"
    },
    {
      "name":            "northwind_knowledge_assistant",
      "description":     "Use this Knowledge Assistant for DOCUMENT Q&A over Northwind Robotics' Employee Handbook, Travel & Expense Policy, and 2024 Sustainability Report. Answers with citations to source PDF/section. Use for PTO, parental leave, conduct, receipt thresholds, travel class, per-diem, mileage, Scope 1/2/3 emissions, sustainability targets, Environmental Steering Committee, handbook-vs-policy conflicts. Do NOT use for NYC taxi data or any structured analytics. Refuses out-of-scope questions (e.g. 401(k)).",
      "ka_tile_id":      "<KA_TILE_ID>"
    }
  ],
  instructions = """
    You are an enterprise supervisor agent coordinating two specialist subagents.

    Routing rules:
    - NYC taxi trip analytics (counts, fares, distances, durations, ZIPs, routes, time-of-day) → nyc_taxi_genie.
    - Northwind Robotics policy / handbook / travel-expense / sustainability questions → northwind_knowledge_assistant.
    - If the user asks a question that spans both domains, call BOTH subagents and synthesize a single answer with clearly labelled sections.
    - If the question fits neither domain, say so explicitly. Do not invent facts.

    Synthesis rules:
    - For mixed questions, structure the answer with H3 headers per subagent so the user can see which source each fact came from.
    - Always include the Knowledge Assistant's citations verbatim when it provides them.
    - For taxi data, include numeric answers with units (USD, miles, minutes) and round monetary values to 2 decimals.
    - If two sources disagree, name the disagreement and identify which subagent produced each claim. Do not silently pick one.

    Refusal posture:
    - The dataset is small and fixed (taxi data ends Feb 29, 2016; Northwind docs are 3 PDFs). For requests outside this scope (e.g. "current date" filters, 401(k), product-specification questions), say the data is not available rather than guessing.
    - Ask a clarifying question when the metric, timeframe, or document area is ambiguous.

    Tone:
    - Be concise. Lead with the direct answer in one sentence; expand only if asked.
    - No emoji. Plain declarative sentences.
  """,
  examples = [
    {"question": "What were the top 5 pickup ZIP codes by valid trip count?",
     "guideline": "Route to nyc_taxi_genie. Return ZIP codes with trip counts. Do not consult the knowledge assistant."},
    {"question": "How many PTO days do employees with 4 years of tenure get?",
     "guideline": "Route to northwind_knowledge_assistant. Include the citation. Do not consult Genie."},
    {"question": "What is the average fare for trips that started in 10001 last month?",
     "guideline": "Route to nyc_taxi_genie. Note that 'last month' relative to the dataset means February 2016."},
    {"question": "Compare our company's CO2 emissions to the trip distances in our taxi data.",
     "guideline": "Call northwind_knowledge_assistant for emissions facts and nyc_taxi_genie for trip-distance summary. Synthesize with the caveat that the two datasets are unrelated business domains."},
    {"question": "What is Northwind's 401(k) employer match?",
     "guideline": "Route to northwind_knowledge_assistant. It will refuse — relay that refusal verbatim. Do not invent."}
  ]
)
```

The response includes a `tile_id` (cache it as `SUPERVISOR_TILE_ID`). The endpoint *name* is **not** returned here — see §3.3.

#### Via CLI (alternative)

```bash
databricks supervisor-agents create-supervisor-agent \
  "enterprise-supervisor-agent" \
  "Routes user questions to the right specialist…" \
  --instructions "<paste the instructions block above>" \
  --json @/tmp/supervisor_payload.json
```

…where `/tmp/supervisor_payload.json` carries the `agents` + `examples` arrays. Field-name details follow the Knowledge Assistant `--json` pattern (see `1_F_knowledge_assistant_page.md` §3.4 for the same footguns: positional + `--json` rejected, exact field name matters).

### 3.3 Look up the serving endpoint name

The `manage_mas` MCP tool doesn't return the endpoint name (only `tile_id`). The CLI list does:

```bash
databricks supervisor-agents list-supervisor-agents \
  | python3 -c '
import json, sys
for s in json.load(sys.stdin):
    print(s.get("display_name"), "→", s.get("endpoint_name"))
'
```

Find the row matching your supervisor's display name; record the `endpoint_name` (pattern `mas-<short-hash>-endpoint`) as `SUPERVISOR_ENDPOINT_NAME` in §1.1.

### 3.4 Grant the App SP `CAN_QUERY` on the supervisor endpoint

Like the KA endpoint, the permissions API needs the endpoint **ID**, not the name. Two-step lookup-and-grant:

```bash
# (a) Endpoint ID for the supervisor:
SUP_EP_ID="$(databricks serving-endpoints get $SUPERVISOR_ENDPOINT_NAME -o json | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"

# (b) App SP client ID:
APP_SP_CLIENT_ID="$(databricks apps get $APP_NAME -o json | python3 -c 'import json,sys; print(json.load(sys.stdin)["service_principal_client_id"])')"

# (c) PATCH (additive — preserves admins / owner entries):
databricks api patch /api/2.0/permissions/serving-endpoints/$SUP_EP_ID --json "{
  \"access_control_list\": [
    {\"service_principal_name\": \"$APP_SP_CLIENT_ID\", \"permission_level\": \"CAN_QUERY\"}
  ]
}"
```

Verify the SP appears with `CAN_QUERY` (not inherited):

```bash
databricks api get /api/2.0/permissions/serving-endpoints/$SUP_EP_ID
```

### 3.5 End-to-end smoke test before touching app code

The supervisor cascades calls to its subagents. Smoke-test the cascade in three steps to localise any 401/403 quickly:

```bash
# Pure Genie route — confirms supervisor → Genie cascade.
databricks api post /serving-endpoints/$SUPERVISOR_ENDPOINT_NAME/invocations \
  --json '{"input":[{"role":"user","content":"What are the top 5 pickup ZIP codes by valid trip count?"}]}' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); [print(p.get("text","")[:200]) for m in d.get("output",[]) for p in (m.get("content") or []) if p.get("type")=="output_text"]'

# Pure KA route — confirms supervisor → KA cascade.
databricks api post /serving-endpoints/$SUPERVISOR_ENDPOINT_NAME/invocations \
  --json '{"input":[{"role":"user","content":"What is the receipt threshold for reimbursable expenses?"}]}' \
  | python3 -c '...same as above...'
```

Expected output from the first call: supervisor planning text → `<name>nyc_taxi_genie</name>` marker → a markdown table of top 5 ZIPs → `<name>enterprise-supervisor-agent</name>` marker → a clean synthesised answer.

If either smoke fails with `Unable to get space` / `permission denied`, the SP is missing one of the three subagent grants from §3.1 — go back and re-verify, do **not** try to fix it at the supervisor layer.

### 3.6 Claude Code prompt — drive §3.1–§3.5 idempotently

```text
Provision the enterprise Supervisor Agent per
docs/plans/1_G_supervisor_page.md.

Inputs from §1.1 + the prior plan worksheets:
- GENIE_SPACE_ID:        <from 0_D_genie_setup.md §1.1>
- KA_TILE_ID:            <from 1_F_knowledge_assistant_page.md §1.1>
- SUPERVISOR_NAME:       enterprise-supervisor-agent
- app_name:              <from databricks.yml resources.apps.streamlit-demo.name>

Do the following idempotently and report each change:

1. Verify the prerequisites by reading three ACLs:
   - /api/2.0/permissions/genie/<GENIE_SPACE_ID>            → SP has CAN_RUN
   - /api/2.0/permissions/serving-endpoints/<KA_ENDPOINT_ID> → SP has CAN_QUERY
   STOP if either grant is missing — go re-run the relevant prior plan.

2. Call manage_mas(action=find_by_name, name=SUPERVISOR_NAME).
   - If found: capture tile_id; do NOT recreate.
   - Else: manage_mas(action=create_or_update, …) with the full agents
     array, instructions, and examples from §3.2 of this plan.
     Capture tile_id.

3. Look up the supervisor endpoint name via
     databricks supervisor-agents list-supervisor-agents
   and print it. Tell me to record it as SUPERVISOR_ENDPOINT_NAME in §1.1.

4. Look up the supervisor endpoint ID and the App SP client ID. PATCH
   /api/2.0/permissions/serving-endpoints/<SUP_EP_ID> to add the SP with
   CAN_QUERY. PATCH is additive — do NOT remove existing ACL entries.

5. Smoke test the three routing paths:
   - Pure Genie:  "What are the top 5 pickup ZIP codes by valid trip count?"
   - Pure KA:     "What is the receipt threshold for reimbursable expenses?"
   - Mixed:       "highest-fare routes, and does the sustainability report mention transport emissions?"
   Print the final synthesis for each. STOP if any returns a partial / 403
   response — describe which subagent failed so I can fix the grant.

Do NOT touch other workspace objects.
```

### 3.7 What to run to initiate

After §3.1–§3.5 succeed and §5 below is committed:

```bash
databricks bundle validate -t dev
databricks bundle deploy  -t dev
databricks bundle run streamlit-demo -t dev
```

The supervisor endpoint is ready as soon as `manage_mas` returns; there's no separate ingestion / sync step like there is for the KA's knowledge source. Permissions take effect immediately.

---

## 4. DAB updates

### 4.1 `databricks.yml`

No required changes. As with the KA endpoint, the supervisor is not a DAB resource type today, and the permission grant is one PATCH call rather than a bundle-managed binding.

If/when the bundle schema ships a `supervisor_agents` or `serving_endpoints` resource that's bindable to an app, you can replace §3.4 with a declarative `apps.<name>.resources` entry of type `serving_endpoint` pointing at the supervisor; for now `app.yaml` carries the endpoint name as a literal `value:`.

### 4.2 `app.yaml`

The only required change — append one entry to `env:`:

```yaml
env:
  # ... existing entries ...

  # Supervisor Agent (Agent Bricks) — routes between the Genie Space + KA.
  # The endpoint speaks OpenAI Responses (`input`, not `messages`).
  - name: SUPERVISOR_ENDPOINT_NAME
    value: "<SUPERVISOR_ENDPOINT_NAME from §1.1>"
```

`SUPERVISOR_ENDPOINT_NAME` is a literal `value:` rather than `valueFrom:` because supervisor endpoints aren't bindable as app resources today. The App SP grants come from §3.4 via REST, not via the bundle.

### 4.3 `pyproject.toml`

No new dependencies. The page uses `requests` (already added in `1_F_knowledge_assistant_page.md` §4.3) and `streamlit` + `databricks-sdk` from the baseline `0_A_initial_setup.md`. If you'd rather use the Databricks-native OpenAI client (`databricks-openai`) for the call, see §5.3's *Adapting* notes — it's a minor refactor.

### 4.4 Redeploy

```bash
databricks bundle validate -t dev
databricks bundle deploy  -t dev
databricks bundle run streamlit-demo -t dev
```

---

## 5. Source code updates

All paths below are relative to the repo root. The page reuses `get_env`, `init_page`, and `workspace_client_app` from `utils.py`.

### 5.1 `app.yaml`

Covered in §4.2 — single `SUPERVISOR_ENDPOINT_NAME` entry.

### 5.2 `app.py` (optional)

Add a one-line bullet to the home-page markdown so users discover the page:

```python
st.markdown(
    "- **Supervisor** — single chat that routes between the NYC Taxi "
    "Genie (structured analytics) and the Northwind Knowledge Assistant "
    "(policy docs), with an audit trail of which subagent answered each "
    "question."
)
```

### 5.3 `pages/7_Supervisor.py`

Create this file with the full contents below. ~170 lines including the trace parser + helpers.

```python
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
```

Key choices to be aware of:

- **`requests.post(...)` not the SDK's `serving_endpoints.query(...)`.** The SDK helper only supports `messages` / `inputs` / `dataframe_records` — supervisor endpoints require the OpenAI Responses-shaped `input` field. Calling REST with `requests` is the minimal-surface-area path and matches `pages/6_Knowledge_Assistant.py`.
- **`workspace_client_app()`, not `workspace_client_obo()`.** The App SP holds `CAN_QUERY` on all three layers; OBO is a separate hardening step (§2 *"Why App SP auth"*).
- **180-second timeout.** Supervisor calls chain tool invocations, so the wall-clock can easily exceed the KA page's 120s default.
- **Trace parsing via `<name>...</name>` markers.** The supervisor encodes speaker boundaries as bare `<name>subagent</name>` text blocks. `_parse_trace()` walks `output[].content[]`, treats those blocks as boundaries, and buckets the surrounding text by speaker. `_final_answer()` returns the last supervisor block as the synthesis.
- **No nested `st.chat_message`.** History rendered at top level before input handling. The new turn opens exactly one user + one assistant chat-message context.
- **Errors persisted as assistant turns.** A 500 from the supervisor doesn't blank the chat — the user sees the error inline and keeps prior context.
- **`SUPERVISOR_NAME` constant** matches the `name` passed to `manage_mas`. If you change the supervisor's name in §3.2 you must update this constant too — otherwise `_final_answer()` never finds a supervisor block and falls back to the last section overall.

### 5.4 Adapting to a different supervisor / subagents

- **Different supervisor.** Update `SUPERVISOR_ENDPOINT_NAME` in `app.yaml` **and** the `SUPERVISOR_NAME` constant in the page to match the new supervisor's `name`. Re-run §3.4 with the new endpoint's ID against the App SP.
- **Add a third subagent.** Append to `agents=[…]` in §3.2's `manage_mas` call (max 20 agents per supervisor). Update §3.1's prerequisite check to verify the SP has the right permission on the new subagent (e.g. `CAN_USE` on a custom-RAG App). The page doesn't change — `<name>new_subagent</name>` boundary markers parse the same way.
- **Switch from `requests` to the Databricks OpenAI client.** Replace `_query_supervisor` with `w.serving_endpoints.get_open_ai_client().responses.create(model=ENDPOINT_NAME, input=[{"role": "user", "content": prompt}])`. Net code is shorter but adds an indirect dependency on the `openai` package (transitively from `databricks-sdk`). The parser stays the same.
- **OBO (production hardening).** Add `user_api_scopes: [serving.serving-endpoints, dashboards.genie, sql]` to the bundle's `apps.streamlit-demo.config` block; swap `workspace_client_app()` for `workspace_client_obo()`; grant `<user_group_app>` (not the SP) on all three layers (supervisor `CAN_QUERY`, KA `CAN_QUERY`, Genie `CAN_RUN`).

---

## Verification

1. **Permissions sanity** — three layers must show explicit grants for the App SP:
   ```bash
   APP_SP="<app_sp_client_id>"
   databricks api get /api/2.0/permissions/serving-endpoints/<SUP_EP_ID> | python3 -c '...print SP entry...'
   databricks api get /api/2.0/permissions/serving-endpoints/<KA_EP_ID>  | python3 -c '...print SP entry...'
   databricks api get /api/2.0/permissions/genie/<GENIE_SPACE_ID>        | python3 -c '...print SP entry...'
   ```
   Expected: `CAN_QUERY` / `CAN_QUERY` / `CAN_RUN`. None should be marked `inherited`.

2. **CLI smoke** — three prompts covering all three routing paths (§3.5).

3. **Static check** from the repo root:
   ```bash
   uv run python -m py_compile app.py utils.py pages/7_Supervisor.py
   ```

4. **Bundle validate**:
   ```bash
   databricks bundle validate -t dev
   ```

5. **Deploy + run**:
   ```bash
   databricks bundle deploy -t dev
   databricks bundle run streamlit-demo -t dev
   ```

6. **Smoke test in browser** — open the app → **Supervisor** in the sidebar. Click each sidebar quick-prompt and verify the routing + synthesis:

   | Prompt | Expected route | Expected synthesis | Trace expander |
   |---|---|---|---|
   | "top 5 pickup ZIP codes by valid trip count" | Genie only | "10001 / 10003 / 10011 / 10021 / 10023" with trip counts + avg fare | 1 step — `nyc_taxi_genie` table |
   | "PTO days at 4 years tenure" | KA only | "24 days" + citation to Handbook §3 | 1 step — `northwind_knowledge_assistant` |
   | "401(k) employer match" | KA, refusal | "Not in the documents" | 1 step — `northwind_knowledge_assistant` no-source refusal |
   | "avg fare per mile by time of day, and travel policy on per-diem" | **Both** | H3 sections: Genie-derived fare-per-mile table + KA-derived per-diem snippet | 2 steps — one per subagent |
   | "highest-fare routes, and sustainability report on transport emissions" | **Both** | H3 sections: Genie routes table + KA Sustainability §2 snippet | 2 steps — one per subagent |

   The last two rows are the most interesting — they prove the fan-out + synthesis path works. The Reasoning expander shows which subagent produced each H3 section, so users can audit cross-domain claims.

7. **Negative test — strip CAN_QUERY on supervisor**:
   ```bash
   databricks api put /api/2.0/permissions/serving-endpoints/<SUP_EP_ID> --json '{"access_control_list":[]}'
   ```
   Next prompt should fail with a 403 directly from the supervisor endpoint. Re-grant via §3.4.

8. **Negative test — strip CAN_QUERY on KA** (leave supervisor + Genie intact):
   ```bash
   databricks api put /api/2.0/permissions/serving-endpoints/<KA_EP_ID> --json '{"access_control_list":[]}'
   ```
   A KA-routed prompt ("PTO days") should now show a PARTIAL response — supervisor planning + KA error inside the trace expander, no final synthesis with the answer. This is the most useful diagnostic for missing subagent grants in production. Re-grant via the KA plan's §3.5.

---

## What to avoid

- **`{"messages": [...]}` body.** The supervisor endpoint rejects it the same way the KA endpoint does. Always send `{"input": [{"role": "user", "content": "..."}]}`.
- **Endpoint name in the permissions PATCH path.** `/api/2.0/permissions/serving-endpoints/<NAME>` returns *"<NAME> is not a valid Inference Endpoint ID."* Always look up the ID first.
- **Granting only on the supervisor endpoint.** The supervisor cascades calls to each subagent on behalf of the same identity. Missing one of the three grants (supervisor / KA / Genie) yields silent partial-fan-out failures that are easy to misdiagnose as "the supervisor is broken".
- **Concatenating the raw response body into the chat bubble.** The user will see `<name>nyc_taxi_genie</name>` markers and Genie's intermediate markdown table mixed with the final synthesis. Parse via `_parse_trace()` and surface only the final supervisor block at top level.
- **Hardcoding the subagent names in the page.** `_parse_trace()` is name-agnostic; only `SUPERVISOR_NAME` is hardcoded (because it's the speaker label used by `_final_answer` to find the synthesis). Changing the supervisor's name in `manage_mas` requires updating that one constant in the page.
- **Skipping SME examples.** A supervisor with rich `instructions` but no `examples` will mis-route ambiguous prompts. The five examples in §3.2 are the minimum baseline; add more as routing failures show up in production.
- **`st.cache_data` on the response.** Chats are per-user; caching globally leaks one user's turns to another. Use `st.session_state`.
- **Nested `st.chat_message`.** Streamlit raises a `StreamlitAPIException`. Render history at top level before opening the new turn's chat-message contexts.
- **Putting the supervisor's full instructions block in `app.yaml`.** It belongs on the supervisor tile (workspace-side), not in the bundle. Editing instructions then redeploying the app is the wrong loop — edit on the supervisor (via `manage_mas` or the UI), no app redeploy needed.
- **Exceeding the 20-agent supervisor cap.** The Agent Bricks UI lets you select up to 30 tools but the documented limit is 20 agents in a single supervisor. Design at or below 20.
