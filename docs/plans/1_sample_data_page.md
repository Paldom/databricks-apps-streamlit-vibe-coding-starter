# Implementation Plan — Sample Data Page (NYC Taxi, curated view)

Page-specific plan for `pages/1_Sample_Data.py` — a Unity Catalog data browser that queries the curated `demo.nyctaxi.v_trips_genie` view on behalf of (OBO) the signed-in user, with sidebar filters, headline metrics, and a formatted table.

> **Prerequisites.**
> - **`0_A_initial_setup.md`** must be done — App, `databricks.yml`, `utils.py`, `app.py`, `app.yaml`, `pyproject.toml`, `uv.lock` already in place; worksheet §1.1 values (`app_name`, `user_group_app`, …) captured.
> - **`0_D_genie_setup.md`** is the recommended prerequisite — it creates the catalog/schema/clone/view this plan reads from (`demo.nyctaxi.v_trips_genie`). If you skip 0_D, fall back to `UNITY_CATALOG_TABLE = samples.nyctaxi.trips` and rewrite the page's `SELECT` + sidebar filters for the raw column shape (`tpep_pickup_datetime`, `fare_amount`, `trip_distance`, integer ZIPs). The page logic is identical; only column names change. See §5.4.

> **DAB-first.** The repo's `databricks.yml` now declares the **SQL Warehouse** as an app resource binding (`apps.streamlit-demo.resources.sql-warehouse`) — so `bundle deploy` automatically grants the App SP `CAN_USE` on the warehouse, replacing the manual "Apps UI → Add resource" step. The UC `SELECT` grant on `demo.nyctaxi.v_trips_genie` is granted to the App SP by `scripts/bootstrap.py` (DAB owns the schema's grants but the view itself is created outside DAB, so its grant lives in the bootstrap script). §3.3 below documents the manual Apps-UI path as an **optional alternative**.

> **Naming convention — shared catalog, monogrammed schema.** UC objects this plan reads live in the **shared `demo` catalog** (pre-existing), inside the operator's per-monogram schema. Use `demo.nyctaxi_${monogram}` (shared catalog + monogrammed schema) and `streamlit-demo-${monogram}` for App / Lakebase resources (hyphen form). **All `demo.nyctaxi.…` literals in the snippets below are placeholders — substitute `demo.nyctaxi_${monogram}.…` everywhere when running for real.** This plan never creates a catalog — `CREATE_CATALOG ON METASTORE` is NOT required.

---

## 1. Parameters to set

Only page-specific knobs. Values already captured in `0_A_initial_setup.md` §1.1 are referenced by name and not re-collected.

| Parameter | Where it lives | Notes |
|---|---|---|
| Table FQN | `app.yaml` env var `UNITY_CATALOG_TABLE` | Three-part Unity Catalog name. Default is the curated Genie view `demo.nyctaxi.v_trips_genie` (16 friendly columns + `valid_trip` flag). |
| SQL Warehouse | DAB var `sql_warehouse_id` + app resource key `sql-warehouse` + `app.yaml` env var `SQL_WAREHOUSE_ID` | The env var resolves through `valueFrom: sql-warehouse` declared in `databricks.yml`. |
| Row cap | In-code constant `ROW_LIMIT` in the page | Upper bound on rows pulled into pandas. The full view is ~22k rows. |
| Page title / icon | `init_page(...)` in the page | Streamlit-rendered. Material Symbols icon names supported. |
| Page filename | `pages/1_Sample_Data.py` | Numeric prefix sets order; underscores become spaces. |
| Schema-specific filters | Sidebar widgets in the page | Default set targets `v_trips_genie` columns; rewrite if you swap to another table. |

### 1.1 Fill-in worksheet

- **`UNITY_CATALOG_TABLE`** = `demo.nyctaxi_${monogram}.v_trips_genie`  *(fallback if 0_D is skipped: `samples.nyctaxi.trips`)*
- **`SQL_WAREHOUSE_ID`** (workspace warehouse ID) = `__________________`
- **`sql-warehouse`** (app resource key bound to the warehouse above) = `sql-warehouse`
- **`ROW_LIMIT`** (in-code constant) = `10000`
- **Page title** = `Sample Data`
- **Page icon** = `:material/local_taxi:`
- **Page filename** = `pages/1_Sample_Data.py`

---

## 2. Overview

**What the page does.** On load, opens a fresh SQL connection scoped to the signed-in user's identity, runs a single `SELECT` against the configured UC view, materialises the result into a pandas DataFrame, and caches it in `st.session_state` for the remainder of the user's session. Sidebar widgets filter the cached DataFrame in-process; headline metrics and the table re-render on every interaction without re-querying. A "Refresh data" button drops the session cache and forces a re-query.

**Why query the curated view, not the raw table.** `demo.nyctaxi.v_trips_genie` already exposes the derived columns the page wants — `duration_minutes`, `fare_per_mile`, `time_of_day`, `pickup_day_of_week`, `route`, `valid_trip` — with UC-level comments and string-typed ZIP codes. The page logic shrinks correspondingly: no pandas-side timestamp arithmetic, no `astype(str)` on ZIPs, just rendering and filters.

**Why OBO.** The connection passes the user's forwarded access token (`X-Forwarded-Access-Token` header) to the SQL warehouse. Unity Catalog enforces row/column policies for that user — the app itself sees only what the user is allowed to see. The page does not need to do permission checks; UC does.

**Why session-state caching, not `st.cache_data`.** Streamlit's built-in `st.cache_data` is a process-wide cache shared across all users hitting the app process. With OBO, that would leak one user's view of the data into another user's session. `st.session_state` is per-user/per-browser-session and is safe.

**End-to-end flow.**
1. Page imports `get_env`, `sql_conn`, `init_page` from `utils.py`.
2. `init_page()` runs `st.set_page_config()`, registers the Databricks logo via `st.logo()`, and renders the signed-in user badge.
3. `get_env("UNITY_CATALOG_TABLE")` reads the FQN from `app.yaml`; halts gracefully if unset.
4. First page-load only: `sql_conn()` opens a DBSQL connection using the user token, the page issues one `SELECT` against the curated view, materialises rows into pandas, and stashes the DataFrame in `st.session_state["trips_df"]`.
5. Subsequent reruns (filter changes) read from session state.
6. Sidebar filters are applied client-side; metrics + table re-render.

**Failure modes the page handles.**
- Missing env var → friendly error via `get_env()` then `st.stop()`.
- Missing user token → friendly error via `get_user_token()` then `st.stop()`.
- Query failure (auth, permission, syntax, view not found) → `st.error(...)` with the exception, then `st.stop()`.
- Empty result → `st.info(...)` then `st.stop()`.

---

## 3. Databricks-side prerequisites

These extend the empty App created in `0_A_initial_setup.md` with the warehouse + UC bindings this page needs. The curated view itself is created by `0_D_genie_setup.md`.

### 3.1 SQL Warehouse
- A running warehouse the signed-in users have `CAN USE` on.
- Record its ID in the worksheet as `SQL_WAREHOUSE_ID`.

### 3.2 Unity Catalog grants
`demo` is a managed catalog created in `0_D_genie_setup.md`, so users do **not** inherit access automatically. Grant the path:

```sql
GRANT USE CATALOG ON CATALOG demo                       TO `<user_group_app>`;
GRANT USE SCHEMA  ON SCHEMA  demo.nyctaxi               TO `<user_group_app>`;
GRANT SELECT      ON VIEW    demo.nyctaxi.v_trips_genie TO `<user_group_app>`;
```

If you're using the `samples.nyctaxi.trips` fallback, these grants are unnecessary — that catalog is world-readable.

### 3.3 App configuration
1. **App resource** — add the SQL Warehouse to the App with key **`sql-warehouse`**. This is what `valueFrom: sql-warehouse` in `app.yaml` resolves against. The DAB block in section 4 declares this; if you are configuring through the Apps UI, add the resource manually.
2. **User-authorization scope** — add **`sql`**. Without it, `X-Forwarded-Access-Token` is not minted with SQL permissions and `sql_conn()` returns 401.

### 3.4 Claude Code prompt — provision page permissions

With the Databricks MCP server connected to Claude Code, paste the prompt below. Fill in the bracketed values from §1.1 above and from `0_A_initial_setup.md` §1.1.

```text
Please provision the Databricks permissions needed by the Sample Data
page described in docs/plans/1_A_sample_data_page.md.

Inputs from the worksheets:
- UNITY_CATALOG_TABLE: <table-fqn, default demo.nyctaxi.v_trips_genie>
- SQL_WAREHOUSE_ID:    <warehouse-id>
- app_name:            <app_name from 0_A_initial_setup.md>
- user_group_app:      <user_group_app from 0_A_initial_setup.md>

Do the following, idempotently (skip if already granted), and report
each change you make:

1. Unity Catalog grants on <UNITY_CATALOG_TABLE> for <user_group_app>:
   - USE CATALOG on the catalog,
   - USE SCHEMA on the catalog.schema,
   - SELECT on the table / view.
   Use the manage_uc_grants MCP tool. Skip catalog/schema steps if the
   table is in `samples.*` (world-readable by default).

2. SQL warehouse <SQL_WAREHOUSE_ID>:
   - Grant CAN_USE to <user_group_app>.

3. Databricks App <app_name>:
   - Ensure an app resource with key `sql-warehouse` is bound to
     warehouse <SQL_WAREHOUSE_ID> with permission CAN_USE.
   - Ensure user authorization is enabled with at least the `sql` scope.
     Do not remove other scopes that may already be present.

4. Verify by running a `SELECT 1 FROM <UNITY_CATALOG_TABLE> LIMIT 1` via
   the SQL MCP tool and printing the result.

Before mutating anything, print the plan of changes and wait for me to
confirm. Do not change grants on objects not listed above.
```

---

## 4. DAB updates

Append to the `databricks.yml` created in `0_A_initial_setup.md`.

### 4.1 New variable
```yaml
variables:
  # ... existing variables ...
  sql_warehouse_id:
    description: "SQL Warehouse ID used by the Sample Data page."
```

### 4.2 App resource binding
Append under `resources.apps.<app_name>.resources`:
```yaml
resources:
  apps:
    <app_name>:
      # ... existing config ...
      resources:
        - name: sql-warehouse
          sql_warehouse:
            id: ${var.sql_warehouse_id}
            permission: CAN_USE
```

### 4.3 Target value
```yaml
targets:
  dev:
    variables:
      sql_warehouse_id: "<your-warehouse-id>"
```

### 4.4 Redeploy
```bash
databricks bundle validate -t dev
databricks bundle deploy -t dev
```

---

## 5. Source code updates

All paths below are relative to the repo root. The page only depends on helpers already exported by `utils.py` after `0_A_initial_setup.md`.

### 5.1 `app.yaml`
Append two entries to `env:`:
```yaml
env:
  # SQL warehouse used by sql_conn()
  - name: SQL_WAREHOUSE_ID
    valueFrom: sql-warehouse                # Resource key declared in databricks.yml
  # Unity Catalog view to visualise (created in docs/plans/0_D_genie_setup.md)
  - name: UNITY_CATALOG_TABLE
    value: "demo.nyctaxi.v_trips_genie"     # Fallback without 0_D: "samples.nyctaxi.trips"
```

### 5.2 `app.py` (optional)
Splice a pointer into the existing home-page markdown so users discover the page:
```python
st.markdown(
    "- **Sample Data** — table viewer over a Unity Catalog view, "
    "queried on behalf of the signed-in user."
)
st.info("👈 Open **Sample Data** in the sidebar.")
```

### 5.3 `pages/1_Sample_Data.py`
Create this file with the full contents below. Tuned for the 16-column curated view; if you fell back to `samples.nyctaxi.trips`, see §5.4 for the column-name swaps.

```python
"""Sample Data - NYC taxi trips from the curated UC view (OBO query)."""
import pandas as pd
import streamlit as st

from utils import get_env, init_page, sql_conn

init_page(page_title="Sample Data", page_icon=":material/local_taxi:")

# Table FQN comes from app.yaml (trusted config, not user input).
TABLE_NAME = get_env("UNITY_CATALOG_TABLE")
ROW_LIMIT = 10_000

st.title("NYC Taxi Trips")
st.caption(
    f"Unity Catalog view `{TABLE_NAME}` — most recent {ROW_LIMIT:,} pickups, "
    f"queried on behalf of the signed-in user."
)


def load_trips(table: str, limit: int) -> pd.DataFrame:
    """Fetch a slice of trips. Table name is from trusted config (app.yaml)."""
    query = (
        f"SELECT pickup_ts, dropoff_ts, "
        f"pickup_zip, dropoff_zip, route, "
        f"trip_distance_miles, fare_amount_usd, "
        f"duration_minutes, fare_per_mile, "
        f"pickup_day_of_week, time_of_day, valid_trip "
        f"FROM {table} "
        f"ORDER BY pickup_ts DESC "
        f"LIMIT {int(limit)}"
    )
    with sql_conn() as conn, conn.cursor() as cur:
        cur.execute(query)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        return df
    df["pickup_ts"] = pd.to_datetime(df["pickup_ts"])
    df["dropoff_ts"] = pd.to_datetime(df["dropoff_ts"])
    return df


# Cache the dataframe per user session — avoids re-querying on every filter
# tweak. Not using st.cache_data: that cache is global across users and would
# leak data when the underlying view has row/column policies.
if "trips_df" not in st.session_state:
    try:
        with st.spinner("Loading taxi data..."):
            st.session_state.trips_df = load_trips(TABLE_NAME, ROW_LIMIT)
    except Exception as exc:
        st.error(f"Failed to query `{TABLE_NAME}`: {exc}")
        st.stop()

df: pd.DataFrame = st.session_state.trips_df

if df.empty:
    st.info(f"No rows returned from `{TABLE_NAME}`.")
    st.stop()

# --- Sidebar filters ---
with st.sidebar:
    st.divider()
    st.markdown("#### Filters")

    pickup_min = df["pickup_ts"].min().date()
    pickup_max = df["pickup_ts"].max().date()
    date_range = st.date_input(
        "Pickup date range",
        value=(pickup_min, pickup_max),
        min_value=pickup_min,
        max_value=pickup_max,
    )

    dist_min = float(df["trip_distance_miles"].min())
    dist_max = float(df["trip_distance_miles"].max())
    dist_range = st.slider(
        "Trip distance (mi)",
        min_value=dist_min,
        max_value=dist_max,
        value=(dist_min, dist_max),
        step=0.1,
    )

    top_pickup_zips = df["pickup_zip"].value_counts().head(20).index.tolist()
    selected_zips = st.multiselect(
        "Pickup ZIP (top 20 by trip count)",
        options=top_pickup_zips,
        default=[],
        help="Empty = all pickup ZIPs.",
    )

    valid_only = st.toggle(
        "Valid trips only",
        value=False,
        help="Drop rows where the view's `valid_trip` flag is false "
        "(non-positive distance, fare, or duration).",
    )

    st.divider()
    if st.button("Refresh data", use_container_width=True):
        st.session_state.pop("trips_df", None)
        st.rerun()

# --- Apply filters client-side ---
mask = pd.Series(True, index=df.index)

if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
    pickup_dates = df["pickup_ts"].dt.date
    mask &= pickup_dates.between(start, end)

mask &= df["trip_distance_miles"].between(dist_range[0], dist_range[1])

if selected_zips:
    mask &= df["pickup_zip"].isin(selected_zips)

if valid_only:
    mask &= df["valid_trip"].fillna(False)

filtered = df.loc[mask]

# --- Headline metrics ---
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Trips", f"{len(filtered):,}")
with c2:
    avg_fare = filtered["fare_amount_usd"].mean() if not filtered.empty else 0.0
    st.metric("Avg fare", f"${avg_fare:,.2f}")
with c3:
    avg_dist = filtered["trip_distance_miles"].mean() if not filtered.empty else 0.0
    st.metric("Avg distance", f"{avg_dist:,.2f} mi")
with c4:
    med_dur = filtered["duration_minutes"].median() if not filtered.empty else 0.0
    st.metric("Median duration", f"{med_dur:.1f} min")

st.divider()

st.dataframe(
    filtered,
    use_container_width=True,
    hide_index=True,
    column_config={
        "pickup_ts": st.column_config.DatetimeColumn(
            "Pickup", format="YYYY-MM-DD HH:mm", width="medium"
        ),
        "dropoff_ts": st.column_config.DatetimeColumn(
            "Dropoff", format="YYYY-MM-DD HH:mm", width="medium"
        ),
        "pickup_zip": st.column_config.TextColumn("Pickup ZIP", width="small"),
        "dropoff_zip": st.column_config.TextColumn("Dropoff ZIP", width="small"),
        "route": st.column_config.TextColumn("Route", width="small"),
        "trip_distance_miles": st.column_config.NumberColumn(
            "Distance (mi)", format="%.2f", width="small"
        ),
        "fare_amount_usd": st.column_config.NumberColumn(
            "Fare", format="$%.2f", width="small"
        ),
        "duration_minutes": st.column_config.NumberColumn(
            "Duration (min)", format="%.1f", width="small"
        ),
        "fare_per_mile": st.column_config.NumberColumn(
            "Fare/mi", format="$%.2f", width="small"
        ),
        "pickup_day_of_week": st.column_config.TextColumn("Day", width="small"),
        "time_of_day": st.column_config.TextColumn("Time of day", width="small"),
        "valid_trip": st.column_config.CheckboxColumn("Valid", width="small"),
    },
)
```

### 5.4 Fallback: targeting `samples.nyctaxi.trips` instead

If 0_D isn't done, swap the page to read the raw sample table — six columns, no derived fields. The page logic stays the same; only column names change.

| Curated view (`demo.nyctaxi.v_trips_genie`) | Raw table (`samples.nyctaxi.trips`) |
|---|---|
| `pickup_ts`, `dropoff_ts` | `tpep_pickup_datetime`, `tpep_dropoff_datetime` |
| `trip_distance_miles` | `trip_distance` |
| `fare_amount_usd` | `fare_amount` |
| `pickup_zip`, `dropoff_zip` (STRING) | `pickup_zip`, `dropoff_zip` (INT) |
| `duration_minutes` (precomputed) | derive: `(dropoff - pickup) / 60` |
| `fare_per_mile` (precomputed) | derive: `fare / distance` |
| `route`, `time_of_day`, `pickup_day_of_week`, `valid_trip` | not available — drop these UI bits |

Practical changes in `pages/1_Sample_Data.py`:

1. `SELECT tpep_pickup_datetime, tpep_dropoff_datetime, trip_distance, fare_amount, pickup_zip, dropoff_zip` and `ORDER BY tpep_pickup_datetime DESC`.
2. After `pd.DataFrame`, derive `trip_duration_min = (df["tpep_dropoff_datetime"] - df["tpep_pickup_datetime"]).dt.total_seconds() / 60.0`.
3. Drop the `valid_trip` toggle and the `route` / `time_of_day` / `pickup_day_of_week` columns from `st.dataframe` `column_config`.
4. `pickup_zip` filter needs `df["pickup_zip"].astype(str).isin(selected_zips)` (the raw column is INT).
5. `column_config` uses `NumberColumn(format="%d")` for the ZIPs instead of `TextColumn`.

The OBO plumbing in `sql_conn()` and the session-state caching pattern do not change.

### 5.5 Adapting to another UC table entirely
1. Set `UNITY_CATALOG_TABLE` in `app.yaml` to the new three-part name.
2. Replace the `SELECT` column list inside `load_trips()` with your columns. Rename the function if helpful.
3. Replace the post-fetch type conversions with anything appropriate for your data.
4. Rewrite the sidebar filters to match your schema (enums, numeric ranges, date columns).
5. Update the headline metrics and `st.dataframe` `column_config` to match.
6. The OBO plumbing in `sql_conn()` and the session-state caching pattern do not change.

---

## Verification

1. **Static check** from the repo root:
   ```bash
   uv run python -m py_compile app.py utils.py pages/1_Sample_Data.py
   ```
2. **Bundle validate** (only if you added the DAB pieces from section 4):
   ```bash
   databricks bundle validate -t dev
   ```
3. **Deploy**:
   ```bash
   databricks bundle deploy -t dev
   ```
4. **Smoke test in browser**
   - Open the app; **Sample Data** appears in the sidebar.
   - Headline metrics render and the table shows up to 10,000 rows.
   - Changing any filter updates metrics and table without spawning a new warehouse query (watch warehouse query history).
   - Toggle **Valid trips only** → row count drops by ~162 (the non-valid rows in the curated view).
   - **Refresh data** triggers exactly one new query.
5. **OBO sanity** — sign in as a user without `SELECT` on `demo.nyctaxi.v_trips_genie`; the page should render `st.error("Failed to query ...")` cleanly, not crash.
