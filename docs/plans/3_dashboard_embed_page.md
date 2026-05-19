# Implementation Plan — Embedded AI/BI Dashboard Page (NYC Taxi)

Page-specific plan for `pages/3_NYC_Taxi_Dashboard.py` — a Streamlit page that embeds a published Databricks AI/BI dashboard inside an iframe. The page itself does **not** query the warehouse; the published dashboard runs with its publisher's credentials, so signed-in app users see the data without needing direct Unity Catalog `SELECT`.

> **Prerequisites.**
> - **`0_A_initial_setup.md`** must be done — App, `databricks.yml`, `utils.py`, `app.py`, `app.yaml`, `pyproject.toml`, `uv.lock` already in place; worksheet §1.1 values (`app_name`, `user_group_app`, …) captured.
> - **`0_D_genie_setup.md`** is **required** — the dashboard reads from `demo.nyctaxi_${monogram}.v_trips_genie` (created in 0_D). If you skip 0_D, change `SOURCE_VIEW` below to your own UC view/table and rebuild the dataset queries.

> **Naming convention — shared catalog, monogrammed schema.** The dashboard reads from the **shared `demo` catalog** + per-operator schema (pre-existing). The dashboard display name should be `NYC Taxi Trips Dashboard (${monogram})` and it queries `demo.nyctaxi_${monogram}.v_trips_genie`. **All `demo.nyctaxi.…` literals in the snippets below are placeholders — substitute `demo.nyctaxi_${monogram}.…` everywhere when running for real.** This plan never creates a catalog — `CREATE_CATALOG ON METASTORE` is NOT required.

---

## 1. Parameters to set

Page-specific knobs; app-level values (`app_name`, `user_group_app`, …) are reused from `0_A_initial_setup.md` §1.1.

| Parameter | Where it lives | Notes |
|---|---|---|
| Dashboard display name | `manage_dashboard(display_name=…)` | Shown in the workspace dashboards list. Spaces and case allowed. |
| Dashboard parent path | `manage_dashboard(parent_path=…)` | Workspace folder that will own the `.lvdash.json` file. Convention: `/Workspace/Users/<your-email>` for personal, `/Workspace/Shared/dashboards` for team use. |
| Dashboard ID | Captured **after** `manage_dashboard(action="create_or_update")` returns | UUID-shaped hex string. Used to build the embed URL. |
| Embed URL | `app.yaml` env var `DASHBOARD_EMBED_URL` | Computed as `https://<WORKSPACE_HOST>/embed/dashboardsv3/<DASHBOARD_ID>`. Note the `embed` path component — **not** `sql`. |
| SQL warehouse | `manage_dashboard(warehouse_id=…)` | Pro or Serverless. AI/BI dashboards do not support Classic. |
| Source view | Dataset SQL inside `serialized_dashboard` | The UC table or view that backs every dataset. |
| Workspace host | `app.yaml` (literal) | Workspace URL, scheme included. |
| Iframe height | In-code constant (`components.iframe(height=…)`) | Tune for the dashboard's grid height. The shipped dashboard runs to `y=23`; height `1100` lets users scroll a small remainder rather than truncating. |
| Page title / icon / filename | `init_page(...)` + filename | Streamlit-rendered. |

### 1.1 Fill-in worksheet

- **`DASHBOARD_NAME`** = `NYC Taxi Trips Dashboard`
- **`DASHBOARD_PARENT_PATH`** = `/Workspace/Users/<your-email>`
- **`DASHBOARD_ID`** (captured after `create_or_update`) = `__________________`
- **`WORKSPACE_HOST`** (from `0_A_initial_setup.md` §1.1, no trailing slash) = `https://__________________`
- **`DASHBOARD_EMBED_URL`** (computed) = `${WORKSPACE_HOST}/embed/dashboardsv3/${DASHBOARD_ID}`
- **`SQL_WAREHOUSE_ID`** (Pro or Serverless) = `__________________`
- **`SOURCE_VIEW`** = `demo.nyctaxi_${monogram}.v_trips_genie`
- **`IFRAME_HEIGHT_PX`** = `1100`
- **Page title** = `NYC Taxi Dashboard`
- **Page icon** = `:material/dashboard:`
- **Page filename** = `pages/3_NYC_Taxi_Dashboard.py`

---

## 2. Overview

**What the page does.** Calls `streamlit.components.v1.iframe(src=DASHBOARD_EMBED_URL, height=1100, scrolling=True)` inside the brand-consistent `init_page()` shell. The iframe loads the published AI/BI dashboard at `/embed/dashboardsv3/<id>`. Because the dashboard is published with `embed_credentials=true`, the visuals are rendered by the workspace using the **publisher's** credentials — the iframe doesn't need the user's OBO token, and app users don't need any UC grants on the source view.

**Why an embedded dashboard, not a custom Plotly page.**

- **No app-side query traffic.** The Streamlit page is essentially static HTML; the warehouse load lives entirely with the dashboard.
- **Full AI/BI feature set for free.** Native filters, drill-down, "ask AI", export, share — all work inside the iframe with no Streamlit code.
- **One source of truth.** Edits made in the workspace dashboard editor instantly propagate to every Streamlit deploy that points at the same embed URL.

**Why `embed_credentials=true`.** Without it, the iframe loads but each visual fails with "no permission" for any user who lacks `SELECT` on the underlying view. With it, the dashboard executes queries as the publisher (the SP / user who ran `create_or_update`), so app users only need:

1. The iframe URL (public — viewing a workspace dashboard still requires being signed in to that workspace).
2. (Optional) `CAN VIEW` on the dashboard object if you also want them to open it standalone.

**Why the curated view as the data source.** `demo.nyctaxi.v_trips_genie` exposes business-friendly column names (`pickup_ts`, `fare_amount_usd`, `time_of_day`, `valid_trip`, …) with UC comments. The dataset SQL inside the dashboard JSON is far easier to read and review against the view than against the raw `samples.nyctaxi.trips` columns.

**End-to-end flow.**

```
demo.nyctaxi.v_trips_genie                 (UC view from 0_D)
        │
        │  6 dataset queries inside serialized_dashboard
        ▼
Lakeview dashboard (workspace asset, .lvdash.json)
        │  manage_dashboard(create_or_update, publish=True, embed_credentials=True)
        ▼
Embed URL:  <WORKSPACE_HOST>/embed/dashboardsv3/<DASHBOARD_ID>
        │
        │  app.yaml DASHBOARD_EMBED_URL  =  the URL above
        ▼
Streamlit page:  init_page() + components.iframe(...)
        ▼
Browser:  iframe renders KPIs + 4 charts + routes table
```

**Failure modes the page handles.**

- Missing `DASHBOARD_EMBED_URL` env var → friendly error via `get_env()` then `st.stop()`.
- Wrong URL path (`/sql/dashboardsv3/...` instead of `/embed/...`) → iframe loads the editor UI, not the read-only viewer.
- Dashboard unpublished or `embed_credentials=false` → iframe renders but visuals show *"No permission"* per widget.

---

## 3. Databricks-side prerequisites and setup

### 3.1 Required privileges and resources

- **SQL warehouse** — Pro or Serverless. Classic warehouses are not supported by AI/BI dashboards. Capture the warehouse ID in §1.1.
- **Source data access** — the user (or service principal) creating the dashboard needs `USE CATALOG` + `USE SCHEMA` + `SELECT` on the source view. Once published with `embed_credentials=true`, end-users do **not** need these grants.
- **Workspace folder** — write access on `DASHBOARD_PARENT_PATH`.

### 3.2 Phase 1 — Test every dataset query before building the JSON

The dashboard JSON references six datasets. **Each query must be validated** against the warehouse before deploying, because widget validation errors are far harder to diagnose after the fact.

Run these in the SQL editor (or MCP `execute_sql`) on your Pro/Serverless warehouse:

```sql
-- summary  (KPIs, single row)
SELECT
  COUNT(*)                                                                  AS trips_total,
  COUNT_IF(valid_trip)                                                      AS trips_valid,
  ROUND(AVG(CASE WHEN valid_trip THEN fare_amount_usd END), 2)              AS avg_fare_usd,
  ROUND(AVG(CASE WHEN valid_trip THEN trip_distance_miles END), 2)          AS avg_distance_miles,
  ROUND(AVG(CASE WHEN valid_trip THEN duration_minutes END), 1)             AS avg_duration_min
FROM demo.nyctaxi.v_trips_genie;

-- by_zip  (top 10 pickup ZIPs by trips)
SELECT pickup_zip, COUNT(*) AS trips, ROUND(AVG(fare_amount_usd), 2) AS avg_fare
FROM demo.nyctaxi.v_trips_genie WHERE valid_trip = true
GROUP BY pickup_zip ORDER BY trips DESC LIMIT 10;

-- by_hour  (trips and avg fare per hour 0-23)
SELECT pickup_hour, ROUND(AVG(fare_amount_usd), 2) AS avg_fare_usd, COUNT(*) AS trips
FROM demo.nyctaxi.v_trips_genie WHERE valid_trip = true
GROUP BY pickup_hour ORDER BY pickup_hour;

-- by_distance  (6 buckets, ordered)
SELECT
  CASE WHEN trip_distance_miles < 1 THEN '0-1 mi'
       WHEN trip_distance_miles < 2 THEN '1-2 mi'
       WHEN trip_distance_miles < 3 THEN '2-3 mi'
       WHEN trip_distance_miles < 5 THEN '3-5 mi'
       WHEN trip_distance_miles < 10 THEN '5-10 mi'
       ELSE '10+ mi' END                                                    AS distance_bucket,
  CASE WHEN trip_distance_miles < 1 THEN 1
       WHEN trip_distance_miles < 2 THEN 2
       WHEN trip_distance_miles < 3 THEN 3
       WHEN trip_distance_miles < 5 THEN 4
       WHEN trip_distance_miles < 10 THEN 5
       ELSE 6 END                                                           AS bucket_order,
  COUNT(*)                                                                  AS trips
FROM demo.nyctaxi.v_trips_genie WHERE valid_trip = true
GROUP BY 1, 2 ORDER BY bucket_order;

-- by_time_of_day  (4 buckets: Morning/Afternoon/Evening/Night)
SELECT time_of_day,
  CASE time_of_day WHEN 'Morning' THEN 1 WHEN 'Afternoon' THEN 2 WHEN 'Evening' THEN 3 WHEN 'Night' THEN 4 END
                                                                            AS bucket_order,
  COUNT(*)                                                                  AS trips,
  ROUND(AVG(fare_amount_usd), 2)                                            AS avg_fare
FROM demo.nyctaxi.v_trips_genie WHERE valid_trip = true
GROUP BY time_of_day ORDER BY bucket_order;

-- top_routes  (top 20 OD pairs with at least 20 trips)
SELECT route, pickup_zip, dropoff_zip,
       COUNT(*)                              AS trips,
       ROUND(AVG(fare_amount_usd), 2)        AS avg_fare_usd,
       ROUND(AVG(trip_distance_miles), 2)    AS avg_distance_miles,
       ROUND(AVG(duration_minutes), 1)       AS avg_duration_min
FROM demo.nyctaxi.v_trips_genie WHERE valid_trip = true
GROUP BY route, pickup_zip, dropoff_zip
HAVING COUNT(*) >= 20
ORDER BY trips DESC LIMIT 20;
```

Expected with the public `samples.nyctaxi.trips` snapshot cloned into `demo`: `trips_total = 21,932`, `trips_valid = 21,770`, `avg_fare_usd ≈ 12.32`, date range `2016-01-01 .. 2016-02-29`.

### 3.3 Phase 2 — Build and publish the dashboard

The dashboard is a single AI/BI dashboard object (`.lvdash.json` under the workspace). It declares six datasets and a 12-column `GRID_V1` layout with 13 widgets. The full JSON shape is reproduced under §4.2 (Reference dashboard JSON).

Three paths to create it, in order of preference:

1. **MCP-driven (recommended)** — paste the §3.4 prompt into Claude Code; the assistant builds + publishes the dashboard using `manage_dashboard(action="create_or_update", publish=True, embed_credentials=True, …)` after re-testing every dataset query.
2. **CLI / SDK** — `databricks api post /api/2.0/lakeview/dashboards --json @dashboard.json` with the same payload, then `databricks api post /api/2.0/lakeview/dashboards/<id>/published` to publish.
3. **Manual UI** — Workspace → Dashboards → Create → Add datasets → Add widgets → Publish → enable "Use publisher credentials". Slowest, but lets a designer iterate visually.

**Whichever path you pick, the publish step must set `embed_credentials=true`**. Without it, the iframe will load but every visual will say *"No permission"* for app users.

### 3.4 Claude Code prompt — build, publish, and hand back the IDs

Paste the prompt below into Claude Code (Databricks MCP server attached). The assistant tests every dataset query, builds the dashboard JSON, publishes with embedded credentials, and prints the IDs ready to paste into §1.1.

```text
Build the NYC Taxi AI/BI dashboard described in
docs/plans/1_C_dashboard_embed_page.md.

Inputs from §1.1:
- DASHBOARD_NAME:         NYC Taxi Trips Dashboard
- DASHBOARD_PARENT_PATH:  /Workspace/Users/<your-email>
- SQL_WAREHOUSE_ID:       <Pro or Serverless warehouse id>
- SOURCE_VIEW:            demo.nyctaxi.v_trips_genie

Do the following idempotently, and print each change:

1. Load the databricks-aibi-dashboards skill so you follow its widget
   JSON shape exactly. Re-validate every one of the six dataset queries
   from §3.2 via execute_sql against SQL_WAREHOUSE_ID. STOP if any
   returns 0 rows or errors out.

2. Build a serialized_dashboard with:
   - 6 datasets (summary, by_zip, by_hour, by_distance, by_time_of_day,
     top_routes) using the exact SQL from §3.2.
   - One PAGE_TYPE_CANVAS page with layoutVersion = GRID_V1.
   - 13 widgets in the layout described in §4.2 of the plan (title,
     subtitle, 3 KPI counters, 2 section headers, 4 charts, 1 table).
     Use widget version 2 for counter/table/textbox, version 3 for
     bar/line. Set disaggregated:true on every query (data is
     pre-aggregated in the dataset SQL).

3. Call manage_dashboard(action="create_or_update",
   display_name=DASHBOARD_NAME, parent_path=DASHBOARD_PARENT_PATH,
   warehouse_id=SQL_WAREHOUSE_ID, publish=True,
   embed_credentials=True, serialized_dashboard=<the json>).

4. Print:
   - the returned dashboard_id,
   - the editor URL (<host>/sql/dashboardsv3/<id>),
   - the embed URL (<host>/embed/dashboardsv3/<id>) — I'll paste this
     into app.yaml `DASHBOARD_EMBED_URL`.

Before mutating anything, print the plan of changes and wait for me to
confirm. Do not touch any other dashboard in the workspace.
```

If you'd rather drive the API directly without Claude Code, the same payload + the `databricks` CLI work:

```bash
# After saving the full dashboard JSON to /tmp/dashboard.json (see §4.2):
databricks api post /api/2.0/lakeview/dashboards \
  --json @/tmp/dashboard.json   # returns {dashboard_id, …}

databricks api post /api/2.0/lakeview/dashboards/<dashboard_id>/published \
  --json '{"warehouse_id": "<warehouse-id>", "embed_credentials": true}'
```

### 3.5 Share the dashboard with app users

`embed_credentials=true` covers data permissions. For app users to *load* the iframe they still need to be signed in to the same workspace. If you also want them to open the dashboard standalone (outside the embed), share it explicitly:

Workspace → Dashboards → *NYC Taxi Trips Dashboard* → **Share** → add `<user_group_app>` from `0_A_initial_setup.md` with `CAN VIEW`.

---

## 4. DAB updates

> **Recommended:** the repo's `databricks.yml` now owns the dashboard via a `resources.dashboards` block that points at `dashboards/nyc_taxi_trips.lvdash.json` in the repo. `bundle deploy` creates/updates it; `bundle destroy` removes it. The §3.3 / §3.4 imperative `manage_dashboard(action="create_or_update", …)` flow remains documented as an **optional alternative** for workspaces without DAB tooling.

### 4.1 `databricks.yml` — shipped DAB shape

```yaml
variables:
  dashboard_parent_path:
    description: "Workspace folder where the AI/BI dashboard `.lvdash.json` is materialised."
  sql_warehouse_id:
    description: "Pro/Serverless warehouse the dashboard queries against."

resources:
  dashboards:
    nyc_taxi_dashboard:
      display_name: NYC Taxi Trips Dashboard
      parent_path: ${var.dashboard_parent_path}
      warehouse_id: ${var.sql_warehouse_id}
      file_path: ./dashboards/nyc_taxi_trips.lvdash.json
      embed_credentials: true     # so app users see data without UC SELECT on the source view

targets:
  dev:
    variables:
      dashboard_parent_path: "/Workspace/Users/<your-email>"
      sql_warehouse_id:      "<warehouse-id>"
```

Run order from a fresh workspace:

1. Bootstrap the source data (`scripts/bootstrap.py` — creates `demo.nyctaxi.v_trips_genie`).
2. **(One-time only — exporting an existing dashboard)** If you're migrating from a workspace-owned dashboard, export its `.lvdash.json` and commit it:
   ```bash
   databricks api get /api/2.0/lakeview/dashboards/<DASHBOARD_ID> \
     | jq -r .serialized_dashboard > dashboards/nyc_taxi_trips.lvdash.json
   ```
   If you're creating from scratch, write a JSON file with the dataset/widget shape from §4.2 below.
3. `databricks bundle deploy -t dev` — DAB calls the same `create_or_update` API the §3.3 path uses, but driven by the local `.lvdash.json`.

**Why `embed_credentials: true` matters here.** `bundle deploy` re-publishes the dashboard on every run; the flag preserves the publisher-credentials mode so the iframe in the Streamlit page keeps working for users without UC `SELECT` on the source view. Forgetting it returns the dashboard to per-viewer credentials.

**App-side dashboard binding.** Databricks Apps' `resources:` schema does **not** support a `dashboard` binding type today. The page reaches the dashboard via the iframe URL in `app.yaml` (`DASHBOARD_EMBED_URL`), not as a runtime app resource — so there's nothing to bind under `apps.streamlit-demo.resources`. If a future DAB release adds it, that's where the binding would go.

### 4.2 Reference dashboard JSON (for `serialized_dashboard`)

Inline reference so you can rebuild the dashboard without leaving this plan. Datasets reproduce §3.2 verbatim; the layout fills a 12-column grid from `y=0` to `y=22` with no gaps.

```python
import json

dashboard = {
    "datasets": [
        {"name": "summary",        "displayName": "Summary KPIs",          "queryLines": ["<see §3.2 summary>"]},
        {"name": "by_zip",         "displayName": "Trips by Pickup ZIP",   "queryLines": ["<see §3.2 by_zip>"]},
        {"name": "by_hour",        "displayName": "Trips and Avg Fare by Hour", "queryLines": ["<see §3.2 by_hour>"]},
        {"name": "by_distance",    "displayName": "Distance Distribution", "queryLines": ["<see §3.2 by_distance>"]},
        {"name": "by_time_of_day", "displayName": "Trips by Time of Day",  "queryLines": ["<see §3.2 by_time_of_day>"]},
        {"name": "top_routes",     "displayName": "Top Routes",            "queryLines": ["<see §3.2 top_routes>"]},
    ],
    "pages": [{
        "name": "overview",
        "displayName": "Overview",
        "pageType": "PAGE_TYPE_CANVAS",
        "layoutVersion": "GRID_V1",
        "layout": [
            # y=0  Title (12x1) — multilineTextboxSpec with one '## NYC Taxi Trips Dashboard' line.
            # y=1  Subtitle (12x1) — dataset + date range + valid_trip caveat.
            # y=2  KPI total trips (4x3) — counter v2, field name 'trips_total', disaggregated true.
            # y=2  KPI avg fare (4x3)    — counter v2, field name 'avg_fare_usd', format number-currency USD.
            # y=2  KPI avg distance (4x3)— counter v2, field name 'avg_distance_miles'.
            # y=5  Section header 'Trends' (12x1).
            # y=6  Line: avg fare by hour (6x5) — bar/line v3, x=pickup_hour quantitative, y=avg_fare_usd quantitative.
            # y=6  Bar: top 10 pickup ZIPs (6x5)— v3, x=pickup_zip categorical, y=trips quantitative.
            # y=11 Bar: distance distribution (6x5) — v3, x=distance_bucket categorical, y=trips quantitative.
            # y=11 Bar: trips by time of day (6x5) — v3, x=time_of_day categorical, y=trips quantitative.
            # y=16 Section header 'Top routes' (12x1).
            # y=17 Table: top 20 routes (12x6) — table v2 with 7 columns
            #              (route, pickup_zip, dropoff_zip, trips, avg_fare_usd, avg_distance_miles, avg_duration_min).
        ],
    }],
}

# Each widget follows this shape (counter example):
counter_kpi = {
    "widget": {
        "name": "kpi-total-trips",
        "queries": [{
            "name": "main_query",
            "query": {
                "datasetName": "summary",
                "fields": [{"name": "trips_total", "expression": "`trips_total`"}],
                "disaggregated": True,
            },
        }],
        "spec": {
            "version": 2,
            "widgetType": "counter",
            "encodings": {"value": {"fieldName": "trips_total", "displayName": "Total trips"}},
            "frame": {"title": "Total trips", "showTitle": True},
        },
    },
    "position": {"x": 0, "y": 2, "width": 4, "height": 3},
}

# Rules to remember:
#  - The `name` inside query.fields MUST exactly match `fieldName` in encodings.
#  - version 2 for counter/table/textbox; version 3 for bar/line/pie.
#  - disaggregated=True when the SQL is already aggregated (every dataset here).
#  - Every page row sums to width=12 exactly. No gaps.
#  - Page must include "layoutVersion": "GRID_V1".

serialized = json.dumps(dashboard)
```

When you call the MCP tool, pass the full object or its JSON string as `serialized_dashboard=`. The tool description also accepts a Python dict directly.

---

## 5. Source code updates

All paths below are relative to the repo root. The page only depends on helpers already exported by `utils.py` after `0_A_initial_setup.md`.

### 5.1 `app.yaml`

Append a single entry to `env:`. The value is the literal embed URL — no `valueFrom:` indirection because dashboards aren't bindable as app resources today in this minimalist setup.

```yaml
env:
  # ... existing entries ...

  # AI/BI dashboard embedded into the NYC Taxi Dashboard page.
  # URL shape: <workspace-host>/embed/dashboardsv3/<dashboard-id>
  # (note the `/embed/` segment — `/sql/` opens the editor view, not the read-only embed).
  - name: DASHBOARD_EMBED_URL
    value: "https://<WORKSPACE_HOST>/embed/dashboardsv3/<DASHBOARD_ID>"
```

Substitute the values captured in §1.1. Re-run `databricks bundle deploy -t dev` (or use Path C from `DEPLOY.md`) to push the change.

### 5.2 `app.py` (optional)

Add a one-line bullet to the home-page markdown so users discover the new page:

```python
st.markdown(
    "- **NYC Taxi Dashboard** — embedded AI/BI dashboard with KPIs, trends, "
    "and a top-routes detail table."
)
```

### 5.3 `pages/3_NYC_Taxi_Dashboard.py`

Create this file with the full contents below. ~25 lines, no SDK calls, no `sql_conn()` — the iframe carries the entire data path.

```python
"""NYC Taxi Dashboard — embedded AI/BI dashboard.

Renders the AI/BI dashboard built over ``demo.nyctaxi.v_trips_genie`` inside
an iframe. The page itself does NOT query the warehouse — the dashboard's
own credentials (published with ``embed_credentials=true``) drive the
visuals, so any signed-in app user can see the data without needing UC
``SELECT`` on the underlying view.
"""
import streamlit as st
import streamlit.components.v1 as components

from utils import get_env, init_page

init_page(page_title="NYC Taxi Dashboard", page_icon=":material/dashboard:")

st.title("NYC Taxi Dashboard")
st.caption(
    "Interactive AI/BI dashboard backed by `demo.nyctaxi.v_trips_genie` — "
    "21,932 trips across Jan 1 – Feb 29, 2016."
)

dashboard_url = get_env("DASHBOARD_EMBED_URL")

# `streamlit.components.v1.iframe` is the supported way to embed iframes in a
# Streamlit app. `st.iframe` does NOT exist; using it raises AttributeError.
# `scrolling=True` lets users scroll inside the iframe when content overflows.
components.iframe(src=dashboard_url, height=1100, scrolling=True)
```

Key choices to be aware of:

- **`components.iframe`, not `st.iframe`.** The latter is a common mis-remembering; it raises `AttributeError`. Use the import path shown.
- **No `sql_conn()` / `workspace_client_*()` import.** The page is pure presentation; the embedded dashboard owns all data access via its publisher credentials.
- **`get_env("DASHBOARD_EMBED_URL")` not a literal URL.** Keeps per-environment URLs (dev vs. staging vs. prod) out of source code — each env supplies its own `app.yaml`.
- **Height tuning.** The shipped dashboard runs to grid row `y=22` (≈ 1300 device pixels). Height `1100` keeps the iframe under most laptop fold lines while letting users scroll the last section. Increase to `1400` for desktop monitors if you don't want the inner scrollbar.

### 5.4 Adapting to another dashboard

Three swap recipes, in order of frequency:

1. **Different dashboard for the same page.** Build the new dashboard (rerun §3.3 with new datasets), capture its new `<dashboard-id>`, update `app.yaml`'s `DASHBOARD_EMBED_URL` to `https://<host>/embed/dashboardsv3/<new-id>`. No code change.
2. **Multiple dashboards.** Add per-dashboard env vars (`DASHBOARD_EMBED_URL_SALES`, `DASHBOARD_EMBED_URL_OPS`, …) and create one `pages/N_…py` per dashboard, each calling `get_env(...)` with its own key. Each page is still ~25 lines.
3. **Per-user / parameterised dashboards.** Append `?param=<value>` to the embed URL via a Streamlit input. AI/BI dashboards support query parameter substitution when the dataset SQL uses `${param}` placeholders. Out of scope for this minimalist plan.

---

## Verification

1. **Source query sanity** — run §3.2 against the warehouse. Expected: `trips_total = 21,932`, `trips_valid = 21,770`, date range `2016-01-01 .. 2016-02-29`. Any wide deviation means the upstream `samples.nyctaxi.trips` snapshot has changed; update the dashboard caption + this plan if so.

2. **Dashboard sanity** — open the editor URL `${WORKSPACE_HOST}/sql/dashboardsv3/${DASHBOARD_ID}` once in the browser. Every widget should render within a few seconds; no red "Invalid widget definition" boxes.

3. **Static check** from the repo root:
   ```bash
   uv run python -m py_compile app.py utils.py pages/3_NYC_Taxi_Dashboard.py
   ```

4. **Bundle validate**:
   ```bash
   databricks bundle validate -t dev
   ```

5. **Deploy**:
   ```bash
   databricks bundle deploy -t dev
   databricks bundle run streamlit-demo -t dev
   ```

6. **Smoke test in browser**
   - Open the app → **NYC Taxi Dashboard** in the sidebar.
   - Wait ~2-3 s for the iframe handshake. Three KPIs appear at the top, two charts side-by-side in the next row, two more below, then the routes table at the bottom.
   - No "X-Frame-Options" / "Refused to display" console errors (the embed path explicitly allows iframing).
   - The dashboard footer should not show a "Sign in" banner; if it does, you used the `/sql/dashboardsv3/...` URL instead of `/embed/dashboardsv3/...` — fix `app.yaml`.

7. **Permission test** — sign in as a user **without** any UC grants on `demo.nyctaxi.v_trips_genie`. They should still see the dashboard render (proving `embed_credentials=true` is active). If individual widgets show *"No permission"*, the dashboard was published with `embed_credentials=false` — republish:
   ```python
   manage_dashboard(action="publish",
                    dashboard_id="<DASHBOARD_ID>",
                    warehouse_id="<SQL_WAREHOUSE_ID>",
                    embed_credentials=True)
   ```

---

## What to avoid

- **`st.iframe(...)`.** It doesn't exist. Use `streamlit.components.v1.iframe` (alias `import streamlit.components.v1 as components` then `components.iframe(...)`).
- **`/sql/dashboardsv3/<id>` in `DASHBOARD_EMBED_URL`.** That's the editor URL; the iframe will load the workspace chrome and prompt the user to sign in. Always use `/embed/dashboardsv3/<id>`.
- **Publishing without `embed_credentials=true`.** Visuals render *"No permission"* for any viewer who lacks UC `SELECT` on the source view — which defeats the point of embedding.
- **Classic SQL warehouse.** AI/BI dashboards refuse to connect. Use Pro or Serverless.
- **Hardcoding the URL inside the page.** Keep it in `app.yaml` so dev/staging/prod can point at different dashboards without code edits.
- **Skipping query validation before building the dashboard JSON.** Widget errors after deploy are opaque ("Invalid widget definition"); a failing `execute_sql` round-trip up front saves an hour of debugging.
- **Mixing `disaggregated:true` and aggregation expressions in the same widget query.** Either pre-aggregate in the dataset SQL and set `disaggregated:true` (this plan's pattern), or leave raw rows in the dataset and use `SUM(...)` / `AVG(...)` aggregations in `query.fields[].expression`. Don't do both — Lakeview will double-aggregate or error out.
- **Forgetting to republish after editing dataset SQL.** Editor-only saves don't update the embedded view. Always re-run `manage_dashboard(action="publish", …)` after a dataset change.
