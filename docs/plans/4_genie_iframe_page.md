# Implementation Plan — Embedded Genie Space Page (NYC Taxi, iframe variant)

Page-specific plan for `pages/4_NYC_Taxi_Genie_iFrame.py` — a Streamlit page that embeds a Databricks Genie Space inside an iframe so users can ask natural-language questions about NYC taxi data without leaving the app. The Streamlit page does **not** call the Genie Conversation API itself; the workspace renders the chat UI inside the iframe.

> **Prerequisites.**
> - **`0_A_initial_setup.md`** must be done — App, `databricks.yml`, `utils.py`, `app.py`, `app.yaml`, `pyproject.toml`, `uv.lock` already in place; worksheet §1.1 values (`app_name`, `user_group_app`, …) captured.
> - **`0_D_genie_setup.md`** is **required** — it creates the Genie Space (`NYC Taxi Trips Genie`) over `demo.nyctaxi.v_trips_genie` that this plan embeds. If you skip 0_D, point `GENIE_SPACE_URL` at any published Genie Space; the page itself is brand-agnostic.

> **Sibling plan.** `1_E_genie_native_page.md` describes the same Genie Space rendered through a custom Streamlit chat UI built on the Databricks SDK's Conversation API. Pick `1_D` for zero maintenance and the full workspace Genie experience; pick `1_E` when you need brand-consistent theming, custom chat behaviour, or the conversation result available as a pandas DataFrame downstream.

---

## 1. Parameters to set

Page-specific knobs; app-level values are reused from `0_A_initial_setup.md` §1.1.

| Parameter | Where it lives | Notes |
|---|---|---|
| Genie Space ID | Captured in `0_D_genie_setup.md` §1.1 | UUID-shaped hex string returned by `create_or_update_genie`. Used to build the embed URL. |
| Workspace host | `app.yaml` (literal) | Workspace URL, scheme included, no trailing slash. |
| Embed URL | `app.yaml` env var `GENIE_SPACE_URL` | Computed as `https://<WORKSPACE_HOST>/embed/genie/rooms/<GENIE_SPACE_ID>`. The `/embed/` segment matters — `/genie/rooms/<id>` is the editor view and may render the workspace chrome / sign-in screen inside the iframe. |
| Iframe height | In-code constant (`components.iframe(height=…)`) | Tune for typical chat lengths. `1100` lets the prompt list + first few turns fit before the inner scrollbar kicks in. |
| Page title / icon / filename | `init_page(...)` + filename | Streamlit-rendered. |

### 1.1 Fill-in worksheet

- **`GENIE_SPACE_ID`** (from `0_D_genie_setup.md` §1.1) = `__________________`
- **`WORKSPACE_HOST`** (from `0_A_initial_setup.md` §1.1) = `https://__________________`
- **`GENIE_SPACE_URL`** (computed) = `${WORKSPACE_HOST}/embed/genie/rooms/${GENIE_SPACE_ID}`
- **`IFRAME_HEIGHT_PX`** = `1100`
- **Page title** = `NYC Taxi Genie`
- **Page icon** = `:material/smart_toy:`
- **Page filename** = `pages/4_NYC_Taxi_Genie_iFrame.py`

---

## 2. Overview

**What the page does.** Calls `streamlit.components.v1.iframe(src=GENIE_SPACE_URL, height=1100, scrolling=True)` inside the brand-consistent `init_page()` shell. The iframe loads the published Genie Space at `/embed/genie/rooms/<id>`; the workspace renders the chat UI in-place. The Streamlit page does no Python work beyond reading the URL from `app.yaml`.

**Why an embedded Genie Space, not a native chat.**

- **Zero maintenance.** Streamlit version upgrades, Genie UI improvements, new attachment types — all show up automatically inside the iframe. The Python code in this app never touches the Conversation API.
- **Full Genie feature set.** Suggested prompts, "Fix it", "Show code", attachment downloads, comments, feedback flags — they're the same UI a user would see in the workspace.
- **No app-side auth choreography.** No SDK imports, no token forwarding, no error handling for 401 / federation-policy failures. Each viewer is signed into the workspace; the iframe inherits their identity.

When this isn't the right choice → see `1_E_genie_native_page.md`. Custom theming, programmatic access to the SQL or DataFrame Genie returns, or non-chat UX flows all need the native variant.

**End-to-end flow.**

```
demo.nyctaxi.v_trips_genie         (UC view from 0_D_genie_setup.md)
        │
        │  attached to Genie Space (also from 0_D)
        ▼
NYC Taxi Trips Genie               (Genie Space, space_id captured in 0_D §1.1)
        │
        │  workspace URL pattern: /embed/genie/rooms/<space_id>
        ▼
app.yaml  GENIE_SPACE_URL          (literal, per-environment)
        │
        │  init_page() + components.iframe(src=GENIE_SPACE_URL, height=1100)
        ▼
Browser:  workspace's own Genie chat UI rendered inside the iframe
```

**Failure modes the page handles.**

- Missing `GENIE_SPACE_URL` env var → friendly error via `get_env()` then `st.stop()`.
- Editor URL (`/genie/rooms/<id>`) instead of embed URL (`/embed/genie/rooms/<id>`) → iframe loads but shows workspace chrome / sign-in prompt. Fix by editing `app.yaml`.
- `X-Frame-Options: DENY` from the workspace → iframe stays blank; the browser console shows the refusal. Use one of the §3.3 fallback URLs.

---

## 3. Databricks-side prerequisites and setup

### 3.1 Required resources

- A **published** Genie Space (created by `0_D_genie_setup.md`). Unpublished spaces don't accept embedded viewers.
- For each end-user of the page:
  - Workspace membership — the iframe inherits the browser's workspace session.
  - `CAN RUN` on the Genie Space (so they can ask questions).
  - `SELECT` on `demo.nyctaxi.v_trips_genie` plus `USE CATALOG demo` + `USE SCHEMA demo.nyctaxi` — Genie executes generated SQL as the viewer.

If `0_D_genie_setup.md` §5.3 was run, the `<user_group_app>` already has all of the above.

### 3.2 Confirm the embed URL pattern

Open the Genie Space in the workspace UI: **Workspace → Genie → NYC Taxi Trips Genie → Share**. Most workspaces expose an "Embed iframe" snippet that already contains the correct URL; copy it verbatim into `app.yaml`. If the Share dialog doesn't have an Embed tab, compute the URL by hand:

```
https://<WORKSPACE_HOST>/embed/genie/rooms/<GENIE_SPACE_ID>
```

`<WORKSPACE_HOST>` is the workspace URL without scheme or trailing slash. `<GENIE_SPACE_ID>` is the hex ID captured in `0_D_genie_setup.md` §1.1.

### 3.3 Fallback URLs if the iframe stays blank

Different Databricks releases have used slightly different embed paths. If the iframe doesn't render, try these in order and redeploy after each:

1. `https://<host>/embed/genie/rooms/<id>` *(default in this plan; mirrors the dashboards `/embed/dashboardsv3/<id>` pattern)*
2. `https://<host>/genie/embed/<id>`
3. `https://<host>/genie/rooms/<id>` *(the standalone editor URL — works when the app and the Genie Space are on the same workspace origin, since `X-Frame-Options: SAMEORIGIN` allows the iframe)*

The Share dialog's snippet is the authoritative source — prefer that over guessing.

### 3.4 Claude Code prompt — confirm the space is shareable

With the Databricks MCP server attached, paste the prompt below. It verifies the Genie Space exists, is published, and is shared with the user group from `0_A_initial_setup.md`. No new infrastructure is created.

```text
Confirm the NYC Taxi Trips Genie Space is ready to embed per
docs/plans/1_D_genie_iframe_page.md.

Inputs:
- GENIE_SPACE_ID:    <from 0_D_genie_setup.md §1.1>
- user_group_app:    <from 0_A_initial_setup.md §1.1>
- source_view:       demo.nyctaxi.v_trips_genie

Do the following idempotently and report each finding:

1. Call get_genie(space_id=GENIE_SPACE_ID). STOP if the space is not
   found — that means 0_D_genie_setup.md has not been completed.

2. Confirm the space is attached to demo.nyctaxi.v_trips_genie and that
   it has a non-empty warehouse_id. Report the warehouse name.

3. Ensure the following UC grants exist for <user_group_app>; create
   any that are missing via manage_uc_grants:
   - USE CATALOG on demo
   - USE SCHEMA  on demo.nyctaxi
   - SELECT      on demo.nyctaxi.v_trips_genie

4. Print the iframe embed URL:
   https://<workspace-host>/embed/genie/rooms/<GENIE_SPACE_ID>
   so I can paste it into app.yaml as GENIE_SPACE_URL.

Do NOT republish the space — embedding works against the published
state from 0_D. Do NOT touch the workspace Genie Space sharing list;
share manually in the Genie UI if access is missing.
```

### 3.5 What I have to run to initiate

After completing §3.1–§3.4 and §5 below:

```bash
databricks bundle validate -t dev
databricks bundle deploy  -t dev
databricks bundle run streamlit-demo -t dev
```

No manual database / dashboard / pipeline trigger is required — the Genie Space is created and published in `0_D_genie_setup.md`. From this plan's perspective the only thing that "happens" is the new page going live.

---

## 4. DAB updates

The Genie Space itself is **not** declared as a DAB resource in this minimalist setup. The bundle only needs to surface the embed URL via `app.yaml`.

### 4.1 `databricks.yml`

No required changes. If you want bundle-managed sharing (so `bundle destroy` revokes the app SP's access), declare the Genie Space as an app resource:

```yaml
resources:
  apps:
    streamlit-demo:
      # ... existing config ...
      resources:
        # ... existing entries ...
        - name: genie-space
          genie_space:
            name: NYC Taxi Trips Genie
            space_id: ${var.genie_space_id}    # add var to variables block
            permission: CAN_RUN
```

This is **not required for the iframe page** — the iframe doesn't go through the App SP — but it's a low-cost addition if you plan to add the native variant (`1_E_genie_native_page.md`) later, since that page does need the SP to have `CAN_RUN`.

### 4.2 Redeploy

Same commands as §3.5. The bundle adds the `GENIE_SPACE_URL` value to the App's env list.

---

## 5. Source code updates

All paths below are relative to the repo root. The page only depends on `get_env()` + `init_page()` from `utils.py` after `0_A_initial_setup.md`.

### 5.1 `app.yaml`

Append a single entry to `env:`. The value is a literal URL — no `valueFrom:` indirection because the URL is just `<workspace-host>/embed/genie/rooms/<id>`, fully resolvable at edit time.

```yaml
env:
  # ... existing entries ...

  # Genie Space embed URL for the iframe-embedded chat page.
  # Workspace UI → Genie → <space> → Share → Embed iframe to confirm the
  # exact path. Pattern: <workspace-host>/embed/genie/rooms/<space-id>.
  - name: GENIE_SPACE_URL
    value: "https://<WORKSPACE_HOST>/embed/genie/rooms/<GENIE_SPACE_ID>"
```

Substitute the values captured in §1.1. Re-run `databricks bundle deploy -t dev` to push the change.

### 5.2 `app.py` (optional)

Add a one-line bullet to the home-page markdown so users discover the new page:

```python
st.markdown(
    "- **NYC Taxi Genie iFrame** — embedded Genie Space; ask natural-language "
    "questions about taxi trips inside an iframe."
)
```

### 5.3 `pages/4_NYC_Taxi_Genie_iFrame.py`

Create this file with the full contents below. ~25 lines, zero SDK imports, no `sql_conn()` — the iframe carries the entire chat path.

```python
"""NYC Taxi Genie — embedded AI/BI Genie Space.

Renders the published Genie Space built over ``demo.nyctaxi.v_trips_genie``
inside an iframe. Users can ask natural-language questions directly in the
embedded chat UI; the Streamlit page itself does NOT call the Genie
Conversation API — Genie runs against the workspace, so any signed-in app
user inherits their own Genie / Unity Catalog permissions on the source view.
"""
import streamlit as st
import streamlit.components.v1 as components

from utils import get_env, init_page

init_page(page_title="NYC Taxi Genie", page_icon=":material/smart_toy:")

st.title("NYC Taxi Genie")
st.caption(
    "Ask natural-language questions about `demo.nyctaxi.v_trips_genie` — "
    "trip counts, fares, distances, durations, pickup / dropoff ZIPs, "
    "routes, and pickup-time trends."
)

genie_url = get_env("GENIE_SPACE_URL")

# `streamlit.components.v1.iframe` is the supported way to embed iframes
# in a Streamlit app. `st.iframe` does NOT exist; using it raises
# AttributeError. `scrolling=True` lets users scroll inside the iframe
# when conversation history grows beyond the viewport.
components.iframe(src=genie_url, height=1100, scrolling=True)
```

Key choices to be aware of:

- **`components.iframe`, not `st.iframe`.** The latter is a common mis-remembering; it raises `AttributeError`. Use the import path shown.
- **No SDK imports.** The page is pure presentation; the workspace owns the chat and the data path.
- **`get_env("GENIE_SPACE_URL")` not a literal URL.** Keeps per-environment URLs (dev vs. staging vs. prod) out of source code.
- **Height tuning.** `1100` is a sane default; the iframe has its own scrollbar so undersize-by-a-bit is preferable to oversize.

### 5.4 Adapting to a different Genie Space

Three swap recipes:

1. **Different Genie Space for the same page.** Update `app.yaml`'s `GENIE_SPACE_URL` with the new embed URL — no code change.
2. **Multiple Genie Spaces.** Add per-space env vars (`GENIE_SPACE_URL_SALES`, `GENIE_SPACE_URL_OPS`, …) and create one `pages/N_…py` per space, each calling `get_env(...)` with its own key. Each page is still ~25 lines.
3. **A space backed by a different UC table / view.** Build the new Genie Space (rerun `0_D_genie_setup.md` against your data), publish it, capture the new ID, swap the URL. No app-side change.

---

## Verification

1. **Genie Space sanity** — open the editor URL `${WORKSPACE_HOST}/genie/rooms/${GENIE_SPACE_ID}` once in the browser. The chat UI loads, sample prompts appear, asking *"What are the top 10 pickup ZIP codes by valid trip count?"* returns a 10-row result with `10001 / 10003 / 10011 / …`.

2. **Static check** from the repo root:
   ```bash
   uv run python -m py_compile app.py utils.py pages/4_NYC_Taxi_Genie_iFrame.py
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

5. **Smoke test in browser**
   - Open the app → **NYC Taxi Genie iFrame** in the sidebar.
   - Wait ~2-3 s for the iframe handshake. The Genie chat UI appears, identical to what `${WORKSPACE_HOST}/genie/rooms/${GENIE_SPACE_ID}` shows.
   - Click one of Genie's suggested prompts — the answer + SQL + result table render inside the iframe.
   - No browser-console `X-Frame-Options: DENY` / *"Refused to display"* errors.

6. **Permission test** — sign in as a user **without** UC `SELECT` on the source view. The iframe still loads but Genie returns *"permission denied"* on query execution. This proves the iframe inherits the viewer's identity (each viewer's grants matter; the iframe does not run with publisher credentials the way dashboards can).

---

## What to avoid

- **`st.iframe(...)`.** It doesn't exist. Use `streamlit.components.v1.iframe` (alias `import streamlit.components.v1 as components` then `components.iframe(...)`).
- **`/genie/rooms/<id>` in `GENIE_SPACE_URL`.** That's the editor URL; the iframe will load the workspace chrome and prompt the user to sign in. Always use the embed path returned by Share → Embed iframe.
- **Hardcoding the URL inside the page.** Keep it in `app.yaml` so dev / staging / prod can point at different Genie Spaces without code edits.
- **Forgetting that the iframe runs with the viewer's identity.** Unlike dashboards (which have `embed_credentials=true`), Genie answers execute as the signed-in user. End-user UC grants on `demo.nyctaxi.v_trips_genie` matter; the app SP's grants don't.
- **Mixing this plan with `1_E_genie_native_page.md` blindly.** They share the Genie Space but use different env vars (`GENIE_SPACE_URL` for iframe, `GENIE_SPACE_ID` for native). Both can coexist — they make different pages — but read `1_E`'s prerequisites before adding the native page on top of this one.
