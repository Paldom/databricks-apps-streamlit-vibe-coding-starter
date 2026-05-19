# Implementation Plan — Knowledge Assistant Page (Northwind PDFs)

Page-specific plan for `pages/6_Knowledge_Assistant.py` — a Streamlit chat UI over a Databricks **Agent Bricks Knowledge Assistant**. The KA itself is the retrieval + answering layer: it ingests PDFs from a Unity Catalog volume, builds the index, answers with citations, and exposes the result as a serving endpoint. The Streamlit page is intentionally thin — it does no RAG plumbing of its own, just chat UI + endpoint invocation + citation rendering.

> **Prerequisites.**
> - **`0_A_initial_setup.md`** must be done — App, `databricks.yml`, `utils.py`, `app.py`, `app.yaml`, `pyproject.toml`, `uv.lock` already in place; worksheet §1.1 values (`app_name`, `user_group_app`, …) captured.
> - **Source documents are this plan's only data prerequisite** — three PDFs of ~5 KB each (the Northwind Robotics test set: Employee Handbook, Travel & Expense Policy, 2024 Sustainability Report). Any PDF / Markdown / DOCX / PPTX set ≤ 50 MB per file works; the page is content-agnostic.

> **Top gotchas (from the implementation).**
> 1. The KA endpoint speaks the **OpenAI Responses API** shape — body field is `input`, **not** `messages`. Sending `messages` returns a 400.
> 2. Knowledge-source JSON uses **`files.path`** (not `files.uri`, not `files_source_spec`). The CLI also rejects positional args + `--json` together — pick one.
> 3. The Postgres-style `databricks api patch /api/2.0/permissions/serving-endpoints/<X>` needs the endpoint **ID** (UUID hash), **not** the endpoint **name**. Look up via `databricks serving-endpoints get <name>`.
> 4. Ingestion of a fresh knowledge source takes **5–15 minutes** even for tiny PDFs. The page handles the in-flight state with a banner.

> **Naming convention — shared catalog, monogrammed schema.** UC objects this plan creates live in the **shared `demo` catalog** (pre-existing), inside the operator's per-monogram schema. The KA display name is `Northwind Knowledge Assistant (${monogram})`, the UC volume backing the PDFs is `demo.knowledge_assistant_${monogram}.docs`, and the serving endpoint name will be auto-generated as `ka-<hash>-endpoint` by the Agent Bricks API — record it after creation. **All `demo.knowledge_assistant.…` literals in the snippets below are placeholders — substitute `demo.knowledge_assistant_${monogram}.…` everywhere when running for real.** This plan never creates a catalog — `CREATE_CATALOG ON METASTORE` is NOT required.

---

## 1. Parameters to set

Page-specific knobs; app-level values are reused from `0_A_initial_setup.md` §1.1.

| Parameter | Where it lives | Notes |
|---|---|---|
| KA display name | `databricks knowledge-assistants create-knowledge-assistant <DISPLAY_NAME> …` | Free-form, must be unique at the workspace level. |
| KA description | Same call, second positional arg | User-facing one-liner shown in the Agents UI. |
| KA instructions | Same call, `--instructions` flag | The system prompt — controls grounding behaviour, refusal posture, citation requirements. |
| KA ID | Returned by `create-knowledge-assistant` (`name = knowledge-assistants/<id>`) | Captured into worksheet; needed to attach sources + sync. |
| Serving endpoint name | Returned by `create-knowledge-assistant` (`endpoint_name`) | What the page invokes. Pattern: `ka-<short-hash>-endpoint`. |
| Serving endpoint ID | Look up via `databricks serving-endpoints get <name>` | Needed for the `CAN_QUERY` PATCH; **endpoint name doesn't work there**. |
| Source volume path | `files.path` JSON field on the knowledge source | Three-part UC volume URI: `/Volumes/<catalog>/<schema>/<volume>`. |
| App SP client ID | `databricks apps get <app_name> -o json` → `.service_principal_client_id` | The identity that calls the endpoint at runtime. Must hold `CAN_QUERY`. |
| Example prompts | In-code `EXAMPLES` tuple in the page | Six sidebar quick-prompts; covers single-hop, cross-document, and out-of-scope refusal. |
| Page title / icon / filename | `init_page(...)` + filename | Streamlit-rendered. |

### 1.1 Fill-in worksheet

- **`KA_DISPLAY_NAME`** = `Northwind Knowledge Assistant`
- **`KA_ID`** (captured after create) = `__________________`
- **`KA_ENDPOINT_NAME`** (captured after create — goes in `app.yaml`) = `__________________`
- **`KA_ENDPOINT_ID`** (lookup after deploy; needed for the permissions PATCH) = `__________________`
- **`SOURCE_VOLUME_CATALOG`** = `demo` *(shared — do not create)*
- **`SOURCE_VOLUME_SCHEMA`** = `knowledge_assistant_${monogram}`
- **`SOURCE_VOLUME_NAME`** = `docs`
- **`SOURCE_VOLUME_PATH`** (computed) = `/Volumes/demo/knowledge_assistant_${monogram}/docs`
- **`app_sp_client_id`** (from `databricks apps get <app_name> -o json`) = `__________________`
- **Page title** = `Knowledge Assistant`
- **Page icon** = `:material/menu_book:`
- **Page filename** = `pages/6_Knowledge_Assistant.py`

---

## 2. Overview

**What the page does.** Renders a brand-consistent chat over a Knowledge Assistant serving endpoint:

1. Reads `KA_ENDPOINT_NAME` from `app.yaml`.
2. Renders prior chat turns from `st.session_state.ka_messages` (each entry can carry a `citations` list rendered inside an expander).
3. On a new prompt (typed or via a sidebar quick-prompt), POSTs to `/serving-endpoints/<endpoint>/invocations` with `{"input": [{"role": "user", "content": <prompt>}]}` and the App SP's OAuth token.
4. Parses the OpenAI Responses-API response: walks `output[].content[]`, collects `output_text` chunks for the answer body and `annotations[]` (`file_citation` / `url_citation`) for citation bullets.
5. Renders the answer + an expandable Citations panel; falls back to an `st.info` banner when `custom_outputs.sources_used` is false (ingestion in progress or out-of-scope refusal).

**Why Knowledge Assistant, not a hand-rolled RAG.** Agent Bricks ships the entire RAG stack: chunking, embedding, vector search, prompting, citation extraction, and a governed serving endpoint. The Streamlit app is now just a UI — no chunker, no embedder, no retrieval prompt, no citation post-processing. SME feedback / guideline curation also lives in the workspace, not in app code.

**Why CAN_QUERY on the serving endpoint (not on the KA object itself).** The KA produces a serving endpoint that owns the answering. Permission on the endpoint controls who can ask questions. The KA object's own permissions control who can edit it — only admins need `Can Manage`; everyone else needs nothing.

**Why session-state caching (not `st.cache_data`).** Each user sees a private chat history. `st.cache_data` is process-global and would leak one user's turns into another user's session. `st.session_state` is per-user/per-browser-session.

**Why `init_page()` not `st.set_page_config()`.** Brand consistency: `init_page()` runs page-config + logo + signed-in user badge in one call (see `0_A_initial_setup.md` §5.2 and `0_B_design_system.md`).

**End-to-end flow.**

```
3 PDFs in this repo's resources/ folder
        │ databricks fs upload (or MCP manage_volume_files)
        ▼
/Volumes/<SOURCE_VOLUME_PATH>             ← managed UC volume
        │ databricks knowledge-assistants create-knowledge-assistant
        │ databricks knowledge-assistants create-knowledge-source (files type, files.path = volume)
        │ databricks knowledge-assistants sync-knowledge-sources
        ▼
Knowledge Assistant + serving endpoint    ← KA_ID + KA_ENDPOINT_NAME captured
        │ databricks api patch /api/2.0/permissions/serving-endpoints/<ID>
        │ (App SP → CAN_QUERY)
        ▼
app.yaml KA_ENDPOINT_NAME = "ka-<hash>-endpoint"
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
Response (OpenAI Responses-API shape):
   output[].content[].text          → assistant markdown
   output[].content[].annotations[] → file_citation / url_citation bullets
   custom_outputs.sources_used      → drives the "no sources" banner
```

**Failure modes the page handles.**

- Missing `KA_ENDPOINT_NAME` env var → friendly `st.error(...)` via `get_env()` then `st.stop()`.
- Endpoint 4xx/5xx → caught and persisted into chat history as an assistant turn plus `st.error(...)`.
- `sources_used == false` + no citations → the `st.info` banner explains *"ingestion may still be in progress — check the Knowledge Source state in the workspace"*.
- Empty `output[]` (shouldn't happen, but defensive) → answer falls back to `(no answer returned)`.

---

## 3. Databricks-side prerequisites and setup

§3.1–§3.5 are the seven concrete steps. §3.6 is a Claude Code prompt that drives all of them idempotently. §3.7 lists each command in copy-paste form for hands-on use.

### 3.1 Required resources

- **Workspace prerequisites** (already true on most workspaces): Unity Catalog enabled, Serverless compute available, Model Serving access, supported region for AI/ML, a serverless usage policy with non-zero budget.
- **Documents** to ingest — placed locally in the project's `resources/` folder for upload. Supported types: `txt`, `pdf`, `md`, `ppt/pptx`, `doc/docx`. Files larger than 50 MB are skipped during ingestion.
- **Deployed Databricks App** — needed so the App SP exists in the workspace and can be granted permissions.

### 3.2 Stage the documents in a UC volume

The `demo` catalog is **shared and pre-existing** — do not create it. Only the per-operator schema + volume below are created here.

```bash
# Per-operator schema inside the shared `demo` catalog
databricks schemas create knowledge_assistant_${monogram} demo \
  --comment "Source documents for the Northwind Knowledge Assistant (${monogram})."

# Volume (managed)
databricks volumes create demo knowledge_assistant_${monogram} docs MANAGED \
  --comment "Northwind Robotics source PDFs for KA ingestion."

# Upload all PDFs from this repo's resources/ folder.
# (Adjust the glob if your source folder isn't ./resources/.)
databricks fs cp -r ./resources/*.pdf dbfs:/Volumes/demo/knowledge_assistant_${monogram}/docs/
```

Equivalent MCP path: `manage_uc_objects(action=create, object_type=schema, …)`, `manage_uc_objects(action=create, object_type=volume, …)`, `manage_volume_files(action=upload, volume_path=…, local_path=./resources/*.pdf)`.

> **Never run `databricks catalogs create --name demo`.** The shared `demo` catalog is provisioned once by a metastore admin. If it doesn't exist, escalate to the metastore admin rather than granting `CREATE_CATALOG` to the operator group.

### 3.3 Create the Knowledge Assistant

The `create-knowledge-assistant` CLI command accepts **two positional args** (display name + description) and a flag for `--instructions`. Keep the instructions tight — they're the agent's system prompt.

```bash
databricks knowledge-assistants create-knowledge-assistant \
  "Northwind Knowledge Assistant" \
  "Answers questions about Northwind Robotics — employee handbook, travel & expense policy, and 2024 sustainability report." \
  --instructions "$(cat <<'EOF'
You are a precise corporate knowledge assistant for Northwind Robotics.

Answer rules:
- Use ONLY the information in the configured knowledge sources.
- Always include citations to the source document and section when possible.
- If the answer is not supported by the sources, say so clearly. Do NOT
  invent facts.
- If two sources conflict, prefer the Travel & Expense Policy over the
  Employee Handbook on expense matters. Otherwise prefer the more
  recent or more specific source.
- Numeric amounts must match the source exactly (PTO days, USD
  per-diem, tCO2e, percentages).
- For ambiguous questions (e.g. mileage rate without a country),
  surface BOTH applicable values and the dependency.
- Keep answers concise: lead with the direct answer in one sentence,
  then a short rationale.
EOF
)"
```

The response includes:

- `id` — the KA UUID. Record as `KA_ID` in §1.1.
- `name` — the full resource name `knowledge-assistants/<id>` (used as the `PARENT` argument when adding sources).
- `endpoint_name` — typically `ka-<short-hash>-endpoint`. Record as `KA_ENDPOINT_NAME`.

### 3.4 Attach the volume as a `files` knowledge source

The `create-knowledge-source` CLI sub-command has a footgun: it rejects positional args + `--json` together, and the source-spec field name is **`files.path`** (not `files.uri`, not `files_source_spec`). The shape below is the one that works.

```bash
cat > /tmp/ka_source.json <<EOF
{
  "display_name": "Northwind PDFs",
  "description": "Employee Handbook, Travel & Expense Policy, Sustainability Report 2024 — three governed PDFs under /Volumes/demo/knowledge_assistant_${monogram}/docs.",
  "source_type": "files",
  "files": {
    "path": "/Volumes/demo/knowledge_assistant_${monogram}/docs"
  }
}
EOF

databricks knowledge-assistants create-knowledge-source \
  "knowledge-assistants/<KA_ID>" \
  --json @/tmp/ka_source.json
```

Then trigger ingestion (the create call kicks one off automatically; this is the explicit re-sync command for later refreshes):

```bash
databricks knowledge-assistants sync-knowledge-sources knowledge-assistants/<KA_ID>
```

Ingestion of three small PDFs takes **5–15 minutes**. The source state goes `UPDATING → READY`.

### 3.5 Grant the App SP `CAN_QUERY` on the serving endpoint

The permissions API needs the **endpoint ID** (a hex hash), not the endpoint name. Two-step lookup-and-grant:

```bash
# (a) Find the endpoint ID:
ENDPOINT_ID="$(databricks serving-endpoints get $KA_ENDPOINT_NAME -o json | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"

# (b) Find the App SP client ID:
APP_SP_CLIENT_ID="$(databricks apps get $APP_NAME -o json | python3 -c 'import json,sys; print(json.load(sys.stdin)["service_principal_client_id"])')"

# (c) PATCH (additive — preserves the existing admins / owner entries):
databricks api patch /api/2.0/permissions/serving-endpoints/$ENDPOINT_ID --json "{
  \"access_control_list\": [
    {\"service_principal_name\": \"$APP_SP_CLIENT_ID\", \"permission_level\": \"CAN_QUERY\"}
  ]
}"
```

Verify the SP is on the ACL with `CAN_QUERY`:

```bash
databricks api get /api/2.0/permissions/serving-endpoints/$ENDPOINT_ID
```

### 3.6 Claude Code prompt — drive §3.2 → §3.5 idempotently

```text
Provision the Northwind Knowledge Assistant per
docs/plans/1_F_knowledge_assistant_page.md.

Inputs from §1.1 + 0_A_initial_setup.md §1.1:
- SOURCE_VOLUME_CATALOG: demo                                (shared — do NOT create)
- SOURCE_VOLUME_SCHEMA:  knowledge_assistant_${monogram}     (per-operator — you create this)
- SOURCE_VOLUME_NAME:    docs
- KA_DISPLAY_NAME:       Northwind Knowledge Assistant (${monogram})
- app_name:              <from databricks.yml resources.apps.streamlit-demo.name>
- local_pdfs:            ./resources/*.pdf

Do the following idempotently and report each change:

1. Confirm the SHARED `demo` catalog exists; DO NOT create it. If it is
   missing, STOP and ask the user to escalate to the metastore admin.
   Then create the UC schema demo.knowledge_assistant_${monogram}
   (skip if exists) and a managed volume demo.knowledge_assistant_${monogram}.docs.

2. Upload every PDF in ./resources/ to /Volumes/demo/knowledge_assistant_${monogram}/docs.
   STOP if 0 files were uploaded.

3. Look for an existing Knowledge Assistant named "Northwind Knowledge
   Assistant (${monogram})" via `databricks knowledge-assistants list-knowledge-assistants`.
   - If it exists: capture its id and endpoint_name; do NOT recreate.
   - Otherwise: create it with the instructions block from §3.3 of the
     plan. Capture id and endpoint_name. Print both and tell me to
     record them in §1.1.

4. List the KA's knowledge sources. If there's no `files` source
   pointing at /Volumes/demo/knowledge_assistant_${monogram}/docs, create one
   with the exact JSON shape from §3.4 (`files.path` field). Then
   trigger `sync-knowledge-sources`.

5. Look up the App SP client ID and the serving-endpoint ID. PATCH the
   serving-endpoint permissions to add the SP with CAN_QUERY (§3.5).
   PATCH is additive — do NOT remove existing ACL entries.

6. Smoke test: POST to the endpoint with
     {"input":[{"role":"user","content":"How many PTO days does an
     employee with 4 years of tenure accrue per year?"}]}
   Print the answer and `custom_outputs.sources_used`. If sources_used
   is False, tell me ingestion is still UPDATING and to retry after
   5–15 minutes — that's expected, not an error.

Do NOT touch other workspace objects, dashboards, or Genie spaces.
```

### 3.7 What to run to initiate

After §3.2–§3.5 succeed and §5 below is committed:

```bash
databricks bundle validate -t dev
databricks bundle deploy  -t dev
databricks bundle run streamlit-demo -t dev
```

Permissions take effect immediately. Re-running `bundle deploy` is idempotent — no state to clean up.

---

## 4. DAB updates

> **Recommended:** the KA tile + knowledge source + endpoint are **still created manually** (Agent Bricks isn't in the DAB schema), but the repo's `databricks.yml` now binds the KA's serving endpoint to the app via `apps.<name>.resources.serving_endpoint`, which makes `bundle deploy` grant `CAN_QUERY` to the App SP automatically. That replaces the manual `databricks api patch /api/2.0/permissions/serving-endpoints/<ID>` step from §3.5. The PATCH path is kept as an **optional alternative** below for workspaces without DAB tooling.

### 4.1 `databricks.yml` — shipped DAB shape

```yaml
variables:
  ka_endpoint_name:
    description: "Knowledge Assistant serving endpoint name (pattern: ka-<hash>-endpoint)."

resources:
  schemas:
    knowledge_assistant:
      catalog_name: demo                 # shared catalog — DAB does NOT create it
      name: knowledge_assistant_${workspace.current_user.short_name}
      grants:
        - principal: ${var.app_sp_client_id}
          privileges: [USE_SCHEMA]

  volumes:
    ka_docs:
      catalog_name: demo                 # shared
      schema_name: ${resources.schemas.knowledge_assistant.name}
      name: docs
      volume_type: MANAGED
      grants:
        - principal: ${var.app_sp_client_id}
          privileges: [READ_VOLUME]

  apps:
    streamlit-demo:
      # ... existing config ...
      resources:
        # ... existing entries ...
        - name: ka-endpoint
          serving_endpoint:
            name: ${var.ka_endpoint_name}
            permission: CAN_QUERY

targets:
  dev:
    variables:
      ka_endpoint_name: "<from §1.1>"
```

What still stays manual (DAB has no resource type for these):

- **Creating the KA tile + its knowledge source + the serving endpoint** — §3.3 / §3.4 of this plan. Agent Bricks artefacts are preview-era and not in DAB.
- **Uploading the PDFs** — `scripts/bootstrap.py` (no DAB volume-file resource).
- **Re-running ingestion when source PDFs change** — `databricks knowledge-assistants sync-knowledge-sources …`.

Don't run both the §3.5 PATCH **and** declare the binding above — `bundle deploy` will keep reconciling its declared state on top of whatever the PATCH left, so a single source of truth (the binding) is cleaner.

### 4.2 `app.yaml`

The only required change — add one entry to `env:`:

```yaml
env:
  # ... existing entries ...

  # Knowledge Assistant (Agent Bricks) — serving endpoint for the
  # Northwind PDFs page.
  - name: KA_ENDPOINT_NAME
    value: "<KA_ENDPOINT_NAME from §1.1>"
```

`KA_ENDPOINT_NAME` is a literal `value:` rather than `valueFrom:` because KA endpoints aren't bindable as app resources today; the App SP gets `CAN_QUERY` via the REST PATCH in §3.5 instead.

### 4.3 `pyproject.toml`

Add `requests>=2.31` (it was a transitive dep before; this makes it explicit so the page's `requests.post(...)` doesn't drift if a future SDK release drops the transitive). Then refresh the lockfile:

```bash
uv lock
```

### 4.4 Redeploy

```bash
databricks bundle validate -t dev
databricks bundle deploy  -t dev
databricks bundle run streamlit-demo -t dev
```

---

## 5. Source code updates

All paths below are relative to the repo root. The page reuses `get_env`, `init_page`, and `workspace_client_app` from `utils.py`.

### 5.1 `pyproject.toml`

```toml
dependencies = [
    "streamlit>=1.57.0",
    "pandas>=2.3.3",
    "databricks-sql-connector>=4.2.6",
    "databricks-sdk>=0.108.0",
    "psycopg[binary,pool]>=3.2",
    "requests>=2.31",
]
```

### 5.2 `app.yaml`

Covered in §4.2 — single `KA_ENDPOINT_NAME` entry.

### 5.3 `app.py` (optional)

Add a one-line bullet to the home-page markdown so users discover the page:

```python
st.markdown(
    "- **Knowledge Assistant** — chat over the Northwind PDFs with "
    "citations, refusal on out-of-scope questions, and an Agent Bricks "
    "managed RAG stack behind the scenes."
)
```

### 5.4 `pages/6_Knowledge_Assistant.py`

Create this file with the full contents below. ~140 lines including comments + two helpers.

```python
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
```

Key choices to be aware of:

- **`requests.post(...)` not the SDK's `serving_endpoints.query(...)`.** The SDK helper only supports `messages` / `inputs` / `dataframe_records` — the KA endpoint requires the OpenAI Responses-shaped `input` field. Calling the REST endpoint with `requests` is the minimal-surface-area path.
- **`w.config.authenticate()` returns the auth headers.** No need to hand-craft `Authorization: Bearer …` — the SDK gives you the dict directly.
- **`workspace_client_app()`, not `workspace_client_obo()`.** The App SP is the identity that holds `CAN_QUERY` on the endpoint. Forwarded user tokens won't have that grant.
- **Responses-API parsing in two layers.** `output[]` carries one or more messages; each message's `content[]` carries one or more typed parts. `output_text` parts contribute to the answer body; their `annotations[]` contribute to the Citations panel.
- **`sources_used` is the "no citations" tell.** When the model legitimately refused (out-of-scope question) **or** when ingestion isn't done yet, `custom_outputs.sources_used` is false. The page surfaces that explicitly so users know the difference between "no answer" and "no sources".
- **No nested `st.chat_message`.** History is rendered top-level before the input handler; the new turn opens exactly two chat-message contexts (user then assistant).
- **Errors are persisted as assistant turns.** A 500 from the endpoint doesn't blank the chat — the user sees the error inline and keeps prior context.

### 5.5 Adapting to a different Knowledge Assistant

- **Different KA.** Update `KA_ENDPOINT_NAME` in `app.yaml`; re-run §3.5 with the new endpoint's ID against the App SP. No code change.
- **Different documents.** Replace the PDFs under `/Volumes/<SOURCE_VOLUME_PATH>` and run `databricks knowledge-assistants sync-knowledge-sources <ka-resource-name>`. Ingestion takes another 5–15 minutes.
- **Different example prompts.** Edit the `EXAMPLES` tuple at the top of the page.
- **Add feedback capture.** Add 👍/👎 buttons under each assistant turn that write into a Delta table (`<catalog>.<schema>.ka_feedback`) using `sql_conn()` from `utils.py`. Out of scope for V1 but a clean follow-up.

---

## Verification

1. **Source state** — wait for ingestion to finish before any user-visible test:
   ```bash
   databricks knowledge-assistants get-knowledge-source \
     knowledge-assistants/<KA_ID>/knowledge-sources/<SOURCE_ID> \
     | jq -r .state
   # Expect: READY (UPDATING → READY in 5–15 min)
   ```

2. **Endpoint smoke test** from the CLI:
   ```bash
   databricks api post /serving-endpoints/<KA_ENDPOINT_NAME>/invocations \
     --json '{"input":[{"role":"user","content":"How many PTO days does an employee with 4 years of tenure accrue per year?"}]}' \
     | jq '.output[0].content[0].text, .custom_outputs.sources_used'
   # Expect: "...24 days..."  true
   ```

3. **Static check** from the repo root:
   ```bash
   uv run python -m py_compile app.py utils.py pages/6_Knowledge_Assistant.py
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

6. **Smoke test in browser** — open the app → **Knowledge Assistant** in the sidebar. Click each sidebar quick-prompt and verify the answers track the underlying PDFs:

   | Prompt | Expected answer | Expected citation |
   |---|---|---|
   | PTO days, 4 years tenure | "24 days" | Employee Handbook §3 |
   | Receipt threshold | "$25" | Handbook §6 / Travel Policy §6 |
   | 6-hour flight class | "Premium Economy" (Director approval to upgrade) | Travel Policy §3 |
   | Scope 2 2023→2024 | "6,800 → 5,400 tCO2e" | Sustainability Report §1 |
   | Handbook vs Travel Policy conflict | "Travel & Expense Policy wins" | Travel Policy §1 |
   | 401(k) match | **Refusal — not in the documents** | (none — `sources_used = false`; the §5.3 banner appears) |

   The last row is the most useful negative test: it confirms the strict instructions are working and the page surfaces the "no sources" state cleanly.

7. **Negative test — strip CAN_QUERY**. Revoke the App SP's `CAN_QUERY`:
   ```bash
   databricks api put /api/2.0/permissions/serving-endpoints/<ID> \
     --json '{"access_control_list":[]}'    # reset to defaults
   ```
   The next prompt should fail with a 403 from the endpoint — proving the SP's explicit grant (not inheritance) is what makes the page work. Re-grant via §3.5.

---

## What to avoid

- **`{"messages": [...]}` body.** The KA endpoint rejects this with *"'messages' field is not supported. Please use 'input' field instead."* Always send `{"input": [{"role": "user", "content": "..."}]}`.
- **Endpoint name in the permissions PATCH path.** `/api/2.0/permissions/serving-endpoints/<NAME>` returns *"<NAME> is not a valid Inference Endpoint ID."* Look up the **ID** via `databricks serving-endpoints get <name>` and use that in the path.
- **`files.uri` / `files_source_spec.uri` in the knowledge-source JSON.** Wrong field names. Use **`files.path`**.
- **Mixing CLI positional args with `--json`** on `create-knowledge-source`. The CLI errors out. Put everything in the JSON file and pass only `PARENT` positionally.
- **Calling the endpoint before ingestion finishes.** It returns *"the search results provided are empty"*. Check `get-knowledge-source … | jq .state` and only flip the user-visible page link on once it reads `READY`.
- **Granting `Can Manage` to all users.** That permission lets users edit the KA's instructions / sources. Restrict to owners. End-users only need `CAN_QUERY` on the serving endpoint.
- **Skipping `CAN_QUERY` because the user is an admin.** When the page runs in the deployed App, it runs as the **App SP**, not as you. The SP needs explicit `CAN_QUERY` independent of who you are. The "Unable to get space" / "permission denied" error class always means the SP, not the human.
- **`st.cache_data` on the response.** Chats are per-user; caching globally leaks one user's turns to another. Use `st.session_state`.
- **Hardcoding the endpoint URL.** Build `f"{w.config.host}/serving-endpoints/{ENDPOINT_NAME}/invocations"` at runtime. Workspace host comes from the SDK; the endpoint name is one env var swap from `app.yaml`.
- **Nested `st.chat_message`.** Streamlit raises a `StreamlitAPIException`. Render history at top level before opening the new turn's chat-message contexts.
