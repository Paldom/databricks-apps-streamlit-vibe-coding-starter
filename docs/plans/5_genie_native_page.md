# Implementation Plan — Native Genie Chat Page (NYC Taxi)

Page-specific plan for `pages/5_NYC_Taxi_Genie_native.py` — a brand-consistent Streamlit chat UI built on the Databricks SDK's **Genie Conversation API**. Same Genie Space as the iframe variant, but rendered with `st.chat_message` / `st.chat_input` instead of an embedded workspace iframe — so theming, sidebar quick-prompts, and downstream access to the SQL + result DataFrame are all under app control.

> **Prerequisites.**
> - **`0_A_initial_setup.md`** must be done — App, `databricks.yml`, `utils.py`, `app.py`, `app.yaml`, `pyproject.toml`, `uv.lock` already in place; worksheet §1.1 values (`app_name`, `user_group_app`, …) captured.
> - **`0_D_genie_setup.md`** is **required** — it creates the Genie Space (`NYC Taxi Trips Genie`) over `demo.nyctaxi.v_trips_genie` that this plan talks to. If you skip 0_D, point `GENIE_SPACE_ID` at any published Genie Space; the page code itself is brand-agnostic.

> **Sibling plan.** `1_D_genie_iframe_page.md` covers the iframe-embed variant of the same Genie Space. Pick `1_D` for zero maintenance and the full workspace Genie UI; pick **this plan (`1_E`)** when you want brand-consistent theming, programmatic access to the answer / SQL / DataFrame, or non-chat-shaped UX that wraps Genie results.

> **Top gotcha.** Unlike the iframe variant — which runs as the viewing user — the native page calls Genie with the **app service principal**'s identity. The SP needs:
> 1. `CAN_RUN` on the Genie Space (explicit, not inherited).
> 2. UC `USE_CATALOG` + `USE_SCHEMA` + `SELECT` along the path to the attached view.
>
> Either one missing produces a `Unable to get space …` error or a `permission denied for table …` once Genie tries to run its generated SQL. §3 below provisions both layers idempotently.

---

## 1. Parameters to set

Page-specific knobs; app-level values are reused from `0_A_initial_setup.md` §1.1.

| Parameter | Where it lives | Notes |
|---|---|---|
| Genie Space ID | `app.yaml` env var `GENIE_SPACE_ID` | The bare hex ID returned by `0_D_genie_setup.md`. **Not** the embed URL — this is the value the Conversation API takes. |
| Source UC view | Configured on the Genie Space itself (§3.2 of `0_D_genie_setup.md`) | This plan inherits whatever view the space points at. App SP UC grants must follow. |
| App SP client ID | `databricks apps get <app-name> -o json` | The Postgres role name + workspace identity the page calls Genie as. Captured once after the first `bundle deploy`. |
| Example prompts | In-code `EXAMPLES` tuple | Six sidebar quick-prompt buttons. Edit per dataset; the shipped set mirrors `0_D_genie_setup.md` §3.7.7. |
| Page title / icon / filename | `init_page(...)` + filename | Streamlit-rendered. |

### 1.1 Fill-in worksheet

- **`GENIE_SPACE_ID`** (from `0_D_genie_setup.md` §1.1) = `__________________`
- **`app_sp_client_id`** (`databricks apps get <app-name> -o json` → `.service_principal_client_id`) = `__________________`
- **`source_uc_view`** (the table/view attached to the Genie Space) = `demo.nyctaxi.v_trips_genie`
- **Page title** = `NYC Taxi Genie (native)`
- **Page icon** = `:material/smart_toy:`
- **Page filename** = `pages/5_NYC_Taxi_Genie_native.py`

---

## 2. Overview

**What the page does.**

1. Reads `GENIE_SPACE_ID` from `app.yaml`.
2. Renders any prior chat turns from `st.session_state.genie_messages` using top-level `st.chat_message(...)` containers.
3. On a new prompt (typed or via a sidebar quick-prompt), calls one of two Conversation API methods through the **app service principal**:
   - `w.genie.start_conversation_and_wait(space_id, content)` — first turn.
   - `w.genie.create_message_and_wait(space_id, conversation_id, content)` — every follow-up.
4. Unpacks the returned `result`:
   - `result.attachments[].text.content` → markdown.
   - `result.attachments[].query.query` → SQL inside a collapsible `st.expander`.
   - `result.query_result.statement_id` → `w.statement_execution.get_statement(...)` → pandas DataFrame from `manifest.schema.columns` + `result.data_array`.
5. Persists the assistant turn back into `st.session_state.genie_messages` so it survives the next rerun (sidebar button clicks, follow-up prompts).

**Why `workspace_client_app()`, not `workspace_client_obo()`.** Genie handles OBO **internally**. Calling the Conversation API with a forwarded user token causes auth failures because Genie re-tries the OBO exchange against a token that already has user identity baked in. The right pattern is to call as the App SP and rely on Genie's own machinery to attribute the request. The page imports `workspace_client_app` and never imports `workspace_client_obo`.

**Why session-state caching (not `st.cache_data`).** Each user sees a private chat history. `st.cache_data` is process-global and would leak one user's turns into another user's session. `st.session_state` is per-user/per-browser-session and is the only safe option for chat UX.

**Why fetching query results in a second SDK call.** Genie returns a `statement_id` in `result.query_result`, not the rows themselves. We call `w.statement_execution.get_statement(statement_id)` to materialise the rows; the manifest gives column names; the `result.data_array` gives the rows. Wrapping both in a single helper (`_df_from_statement`) keeps the assistant block readable.

**Why no nested `st.chat_message`.** Streamlit raises if `st.chat_message` is called inside another `st.chat_message` context. The page renders history at top level **before** handling the new prompt, then opens exactly two chat-message contexts for the new turn (user + assistant). No nesting anywhere.

**End-to-end flow.**

```
app.yaml          GENIE_SPACE_ID = "<hex>"
        │
        ▼
init_page() + st.session_state.setdefault(...)         ← bootstrap
        │
        ▼
sidebar: 6 quick-prompt buttons   │   "Clear conversation"
        │                          │
        │ click → st.session_state["_genie_prefill"] = ex; st.rerun()
        ▼
for msg in genie_messages:                              ← render history
    with st.chat_message(msg.role):
        markdown + expander(SQL) + dataframe
        │
        ▼
prefill or chat_input → prompt
        │
        ▼
st.session_state.genie_messages.append({"role": "user", "content": prompt})
with st.chat_message("user"):
    st.markdown(prompt)
        │
        ▼
w = workspace_client_app()                              ← App SP, NOT OBO
result = w.genie.start_conversation_and_wait(...)        ← first turn
       or w.genie.create_message_and_wait(...)           ← follow-up
        │
        ▼
extract attachments → text + SQL
extract result.query_result.statement_id → DataFrame
        │
        ▼
render in `st.chat_message("assistant")` + persist to genie_messages
```

**Failure modes the page handles.**

- Missing `GENIE_SPACE_ID` env var → friendly error via `get_env()` then `st.stop()`.
- Genie API exception (missing CAN_RUN, missing UC grant, space unpublished, warehouse stopped) → `st.error(...)` and the error text persisted as an assistant turn so the user has context.
- Empty attachments (Genie returns text-only or refuses) → the page falls back to `"Done."` so the assistant always renders something visible.
- Sidebar quick-prompt clicked → `_genie_prefill` carries the value through `st.rerun()` and is consumed by the next input handler — no duplicate send.

---

## 3. Databricks-side prerequisites and setup

§3.1 covers the workspace requirements. §3.2 grants `CAN_RUN` on the Genie Space to the app SP (the critical gotcha). §3.3 grants UC privileges along the source-view path (the second-layer gotcha). §3.4 is a single Claude Code prompt that does both layers idempotently. §3.5 lists the commands to run if you'd rather drive it by hand.

### 3.1 Required resources

- A **published** Genie Space from `0_D_genie_setup.md`.
- The Pro/Serverless SQL warehouse attached to that space, running.
- A deployed Databricks App from `0_A_initial_setup.md` — needed so the app SP exists in the workspace and can be granted permissions.

### 3.2 Grant the app SP `CAN_RUN` on the Genie Space

This is the single permission that the iframe variant doesn't need. Without it, the Conversation API rejects every call with:

> *Unable to get space [...]. Caused by User <sp-uuid> does not have read permission for node with aclPath /workspace/.../genie/...*

Find the app SP client ID once, then PATCH the Genie permissions ACL:

```bash
APP_NAME="<from databricks.yml resources.apps.streamlit-demo.name>"
APP_SP_CLIENT_ID="$(databricks apps get "$APP_NAME" -o json \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["service_principal_client_id"])')"

# Add (PATCH is additive — existing ACL entries are preserved):
databricks api patch /api/2.0/permissions/genie/${GENIE_SPACE_ID} \
  --json "{
    \"access_control_list\": [
      {\"service_principal_name\": \"${APP_SP_CLIENT_ID}\", \"permission_level\": \"CAN_RUN\"}
    ]
  }"

# Verify the SP is now listed with CAN_RUN:
databricks api get /api/2.0/permissions/genie/${GENIE_SPACE_ID}
```

Object type is `genie`, object path is `/api/2.0/permissions/genie/<space-id>`. PATCH semantics are additive; no need to fetch the existing ACL and resend the whole list.

### 3.3 Grant the app SP UC access along the source-view path

Once `CAN_RUN` is in place, the SDK call returns the Genie Space's reply — but **Genie then executes its generated SQL with the caller's UC identity**. So the SP also needs:

```sql
GRANT USE CATALOG ON CATALOG demo                       TO `<app_sp_client_id>`;
GRANT USE SCHEMA  ON SCHEMA  demo.nyctaxi               TO `<app_sp_client_id>`;
GRANT SELECT      ON VIEW    demo.nyctaxi.v_trips_genie TO `<app_sp_client_id>`;
```

If you've already granted `<user_group_app>` these privileges in `0_D_genie_setup.md` §5.3, that does **not** cover the app SP unless you also add the SP to that group. The cleanest path is the direct grant above.

### 3.4 Claude Code prompt — provision both layers

With the Databricks MCP server attached, paste the prompt below. It captures the SP client ID, PATCHes the Genie Space ACL, and applies the UC grants — idempotent on re-run.

```text
Provision the permissions the Native Genie Chat page needs per
docs/plans/1_E_genie_native_page.md.

Inputs from §1.1 + 0_A_initial_setup.md §1.1:
- app_name:        <from databricks.yml resources.apps.streamlit-demo.name>
- GENIE_SPACE_ID:  <from 0_D_genie_setup.md §1.1>
- source_uc_view:  demo.nyctaxi.v_trips_genie

Do the following idempotently and report each change:

1. Resolve the app service-principal client ID:
     databricks apps get <app_name> -o json
   Extract `service_principal_client_id`. Print it; I'll need it for the
   page worksheet.

2. Add the SP to the Genie Space ACL with CAN_RUN by PATCHing:
     /api/2.0/permissions/genie/<GENIE_SPACE_ID>
   Body:
     {"access_control_list":[{"service_principal_name":"<sp_client_id>","permission_level":"CAN_RUN"}]}
   PATCH is additive — do not remove existing ACL entries.
   Verify with a GET on the same path.

3. Using the manage_uc_grants MCP tool, grant the SP these privileges
   (idempotent — re-running is fine):
   - USE_CATALOG on CATALOG demo
   - USE_SCHEMA  on SCHEMA  demo.nyctaxi
   - SELECT      on TABLE   demo.nyctaxi.v_trips_genie

4. Verify by calling Genie as the SP using a one-shot Python script:
       from databricks.sdk import WorkspaceClient
       w = WorkspaceClient()
       r = w.genie.start_conversation_and_wait(space_id="<GENIE_SPACE_ID>",
                                                content="What are the top 5 pickup ZIPs?")
       print(r.attachments[0].text.content if r.attachments else r)
   Run it. STOP if it fails — the page won't work either.

Do NOT touch other workspace objects.
```

### 3.5 What to run to initiate

After §3.4 succeeds and §5 below is committed:

```bash
databricks bundle validate -t dev
databricks bundle deploy  -t dev
databricks bundle run streamlit-demo -t dev
```

Permissions take effect immediately — no app restart needed if the grants were the only change. If you redeployed code as well, the bundle run picks it up.

---

## 4. DAB updates

The Genie Space is created in `0_D_genie_setup.md` and lives as a workspace asset, **not** as a DAB resource here. This plan needs only one tiny `app.yaml` env entry.

### 4.1 `databricks.yml`

No required changes. If you want bundle-managed Genie permissions (so `bundle destroy` revokes the SP's `CAN_RUN`), declare the space as an app resource:

```yaml
variables:
  genie_space_id:
    description: "Genie Space ID for the Native Genie Chat page."

resources:
  apps:
    streamlit-demo:
      # ... existing config ...
      resources:
        # ... existing entries ...
        - name: genie-space
          genie_space:
            name: NYC Taxi Trips Genie
            space_id: ${var.genie_space_id}
            permission: CAN_RUN
```

…with a value under `targets.dev.variables`:

```yaml
targets:
  dev:
    variables:
      genie_space_id: "<from 0_D_genie_setup.md §1.1>"
```

This is **optional** — §3.2's `databricks api patch ...` already grants `CAN_RUN`. The DAB binding is just a bookkeeping mechanism so future `bundle destroy` cleans up the grant too. Don't both PATCH and declare the binding unless you want one to be the source of truth (pick the binding).

### 4.2 `app.yaml`

The only required change is in `app.yaml`, under `env:`. The native page uses the bare Genie Space ID; the iframe page (`1_D`) uses the URL. Both can coexist as separate entries.

```yaml
env:
  # ... existing entries ...

  # Genie Space ID for the native Conversation-API chat page.
  # (The iframe variant uses GENIE_SPACE_URL instead.)
  - name: GENIE_SPACE_ID
    value: "<GENIE_SPACE_ID from 0_D_genie_setup.md §1.1>"
```

### 4.3 Redeploy

Same commands as §3.5.

---

## 5. Source code updates

All paths below are relative to the repo root. The page reuses `get_env`, `init_page`, and `workspace_client_app` from `utils.py`.

### 5.1 `app.yaml`

Covered in §4.2 — single `GENIE_SPACE_ID` entry.

### 5.2 `app.py` (optional)

Add a one-line bullet to the home-page markdown so users discover the page:

```python
st.markdown(
    "- **NYC Taxi Genie native** — Genie Conversation API rendered as a "
    "native Streamlit chat, with sidebar quick-prompts and an expandable "
    "SQL preview."
)
```

### 5.3 `pages/5_NYC_Taxi_Genie_native.py`

Create this file with the full contents below. ~130 lines including comments + the `_df_from_statement` helper.

```python
"""NYC Taxi Genie (native) — chat UI over the Databricks Genie Conversation API.

Uses ``workspace_client_app()`` (the app's service principal, **not** OBO)
because the Conversation API handles OBO internally. The page renders a
native Streamlit chat — full theming control, sample-prompt buttons in the
sidebar, expandable SQL block, and the result set as an
``st.dataframe``.

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
```

Key choices to be aware of:

- **`workspace_client_app()`, not `workspace_client_obo()`.** Genie's Conversation API does OBO internally; passing the forwarded user token causes 401s. The auth identity here is the app SP — make sure §3.2 + §3.3 grants cover the SP, not the end-user.
- **`st.session_state.setdefault(...)`** is the idiomatic per-key initialiser; cleaner than `if key not in st.session_state: …`.
- **Quick-prompt prefill via `_genie_prefill` + `st.rerun()`.** Clicking a sidebar button puts the prompt into session-state and triggers a rerun. The next render pops it and treats it identically to a typed prompt — no parallel code path for sidebar prompts.
- **History rendered before input handling.** Means new sidebar clicks don't double-render the most-recent turn. The new turn is rendered exactly once inside the input-handling block.
- **`_df_from_statement` is a tiny helper.** Genie returns a `statement_id`; the rows come from a follow-up `statement_execution.get_statement(...)`. Wrapping that in a helper makes the assistant block read top-to-bottom.
- **No nested `st.chat_message`.** The history loop opens one chat-message context per past turn at top level; the new turn opens one `chat_message("user")` then one `chat_message("assistant")` — never nested. Streamlit raises if you try.
- **Errors persisted as an assistant turn.** Avoids the bewildering experience of an empty chat after a failed call; the next prompt has the previous error visible above it for context.

### 5.4 Adapting to another Genie Space / customisations

- **Different Genie Space.** Update `GENIE_SPACE_ID` in `app.yaml`. Also re-run §3.2 + §3.3 on the new space + its source view. No code change.
- **Different example prompts.** Edit the `EXAMPLES` tuple at the top of the page.
- **Add a "history download" button.** Use `st.download_button(...)` with `json.dumps(st.session_state.genie_messages, default=str)` — but strip the `dataframe` entries first (they're pandas objects).
- **Stream tokens instead of waiting.** Replace `start_conversation_and_wait` / `create_message_and_wait` with the non-blocking `start_conversation` + polling, and write into `st.chat_message("assistant")` with `st.write_stream(...)`. Out of scope for this minimalist plan.

---

## Verification

1. **Permissions sanity** — confirm both layers are in place:
   ```bash
   # Genie Space ACL — the SP must appear with CAN_RUN
   databricks api get /api/2.0/permissions/genie/${GENIE_SPACE_ID} \
     | python3 -c 'import json,sys;d=json.load(sys.stdin);[print(e.get("service_principal_name") or e.get("user_name") or e.get("group_name"),[p["permission_level"] for p in e["all_permissions"]]) for e in d["access_control_list"]]'
   ```
   The output should include a line for `${APP_SP_CLIENT_ID}` with `['CAN_RUN']` (NOT inherited).

2. **Static check** from the repo root:
   ```bash
   uv run python -m py_compile app.py utils.py pages/5_NYC_Taxi_Genie_native.py
   ```

3. **Bundle validate**:
   ```bash
   databricks bundle validate -t dev
   ```

4. **Deploy**:
   ```bash
   databricks bundle deploy -t dev
   databricks bundle run streamlit-demo -t dev
   ```
   *Permissions take effect immediately; no app restart needed if you only changed grants. If `bundle run` was already done after the grants, hard-refresh the browser to pick up new auth state.*

5. **Smoke test in browser**
   - Open the app → **NYC Taxi Genie native** in the sidebar.
   - Click *"What are the top 10 pickup ZIP codes by valid trip count?"* from the sidebar.
   - Within ~3 seconds expect: an assistant prose answer, an expandable **SQL query** block with Genie's generated `SELECT pickup_zip, COUNT(*) … LIMIT 10`, and a 10-row dataframe with `10001 / 10003 / 10011 / …` matching the §3.5 profile of `0_D_genie_setup.md`.
   - Type a follow-up like *"now group by pickup_hour"*. Genie reuses the existing `conversation_id`, so the answer should reference the previous question.
   - Click **Clear conversation** in the sidebar → next prompt starts a fresh conversation (visible in the app log: a new `start_conversation_and_wait` call vs `create_message_and_wait`).

6. **Negative test — strip `CAN_RUN`**:
   - Run `databricks api patch /api/2.0/permissions/genie/${GENIE_SPACE_ID}` with an ACL that omits the SP. The next prompt must fail with *"Unable to get space …"* — proving the SP's explicit `CAN_RUN` (not inheritance) is what makes the page work.
   - Re-add `CAN_RUN` (re-run §3.4).

7. **Negative test — revoke UC `SELECT`**:
   - `REVOKE SELECT ON VIEW demo.nyctaxi.v_trips_genie FROM \`<sp_client_id>\``.
   - The next prompt should still let Genie answer in prose + show the generated SQL, but the dataframe will be missing / Genie may report a permission error.
   - Re-grant the privilege.

---

## What to avoid

- **`workspace_client_obo()` for Genie calls.** Genie's Conversation API does OBO internally; forwarded user tokens produce 401s. Always `workspace_client_app()` here. (Contrast with `1_A_sample_data_page.md`, where the SQL warehouse path uses OBO.)
- **Relying on inherited workspace permissions for the Genie Space ACL.** The Genie Space lives under a workspace directory whose ACL may already grant `CAN_RUN` to groups your SP doesn't belong to (e.g. `Databricks Training Guests`). The SP needs an **explicit** ACL entry — that's what §3.2's PATCH adds.
- **Granting UC privileges only to `<user_group_app>`.** End-user grants do not extend to the App SP unless the SP is in that group. Add the SP either to the group (§5.3 of `0_D_genie_setup.md`) or via a direct grant (§3.3 of this plan).
- **`st.cache_data` on the response.** Chats are per-user; caching globally leaks one user's turns to another. Use `st.session_state` for everything chat-related.
- **Nested `st.chat_message`.** Streamlit raises a `StreamlitAPIException`. Render history at top level before opening the new turn's chat-message contexts.
- **Hardcoding the conversation_id.** Always store/read it from session state; Genie's conversation IDs are server-issued and rotating per session.
- **Forgetting to persist the assistant turn.** Rendering an `st.chat_message("assistant")` inline shows it once; without appending to `genie_messages` the next sidebar click rerenders an empty assistant slot. Always do both — inline render + append to history.
- **Using the embed URL (`/embed/genie/rooms/<id>`) as `GENIE_SPACE_ID`.** That's the iframe variant. The Conversation API expects the bare hex ID.
