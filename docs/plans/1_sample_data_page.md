# Implementation Plan — Sample Data Page (NYC Taxi)

Page-specific plan for `pages/1_Sample_Data.py` — a Unity Catalog data browser that queries a UC table on behalf of (OBO) the signed-in user, with sidebar filters, headline metrics, and a formatted table.

> **Prerequisite.** Complete `0_initial_setup.md` first. This plan assumes the App, `databricks.yml`, `utils.py`, `app.py`, `app.yaml`, and `requirements.txt` are already in place and that the worksheet values from §1.1 of that doc (`app_name`, `user_group_app`, etc.) are recorded.

---

## 1. Parameters to set

Only page-specific knobs. Values already captured in `0_initial_setup.md` §1.1 are referenced by name and not re-collected.

| Parameter | Where it lives | Notes |
|---|---|---|
| Table FQN | `app.yaml` env var `UNITY_CATALOG_TABLE` | Three-part Unity Catalog name. Change the column list inside the page if you swap tables. |
| SQL Warehouse | DAB var `sql_warehouse_id` + app resource key `sql-warehouse` + `app.yaml` env var `SQL_WAREHOUSE_ID` | The env var resolves through `valueFrom: sql-warehouse` declared in `databricks.yml`. |
| Row cap | In-code constant `ROW_LIMIT` in the page | Upper bound on rows pulled into pandas. The full sample table is ~22k rows. |
| Page title / icon | `st.set_page_config(...)` in the page | Streamlit-rendered. Material Symbols icon names supported. |
| Page filename | `pages/1_Sample_Data.py` | Numeric prefix sets order; underscores become spaces. |
| Schema-specific filters | Sidebar widgets in the page | Rewrite to fit your columns if you swap tables. |

### 1.1 Fill-in worksheet

- **`UNITY_CATALOG_TABLE`** = `samples.nyctaxi.trips`
- **`SQL_WAREHOUSE_ID`** (workspace warehouse ID) = `__________________`
- **`sql-warehouse`** (app resource key bound to the warehouse above) = `sql-warehouse`
- **`ROW_LIMIT`** (in-code constant) = `10000`
- **Page title** = `Sample Data`
- **Page icon** = `:material/local_taxi:`
- **Page filename** = `pages/1_Sample_Data.py`

---

## 2. Overview

**What the page does.** On load, opens a fresh SQL connection scoped to the signed-in user's identity, runs a single `SELECT` against the configured UC table, materializes the result into a pandas DataFrame, and caches it in `st.session_state` for the remainder of the user's session. Sidebar widgets filter the cached DataFrame in-process; headline metrics and the table re-render on every interaction without re-querying. A "Refresh data" button drops the session cache and forces a re-query.

**Why OBO.** The connection passes the user's forwarded access token (`X-Forwarded-Access-Token` header) to the SQL warehouse. Unity Catalog enforces row/column policies for that user — the app itself sees only what the user is allowed to see. The page does not need to do permission checks; UC does.

**Why session-state caching, not `st.cache_data`.** Streamlit's built-in `st.cache_data` is a process-wide cache shared across all users hitting the app process. With OBO, that would leak one user's view of the data into another user's session. `st.session_state` is per-user/per-browser-session and is safe.

**End-to-end flow.**
1. Page imports `get_env`, `sql_conn`, `render_sidebar` from `utils.py`.
2. `render_sidebar()` renders the logo + signed-in user badge.
3. `get_env("UNITY_CATALOG_TABLE")` reads the FQN from `app.yaml`; halts gracefully if unset.
4. First page-load only: `sql_conn()` opens a DBSQL connection using the user token, the page issues one `SELECT`, materializes rows into pandas, computes a derived `trip_duration_min` column, and stashes the DataFrame in `st.session_state["trips_df"]`.
5. Subsequent reruns (filter changes) read from session state.
6. Sidebar filters are applied client-side; metrics + table re-render.

**Failure modes the page handles.**
- Missing env var → friendly error via `get_env()` then `st.stop()`.
- Missing user token → friendly error via `get_user_token()` then `st.stop()`.
- Query failure (auth, permission, syntax) → `st.error(...)` with the exception, then `st.stop()`.
- Empty result → `st.info(...)` then `st.stop()`.

---

## 3. Databricks-side prerequisites

These extend the empty App created in `0_initial_setup.md` with the warehouse + UC bindings this page needs.

### 3.1 SQL Warehouse
- A running warehouse the signed-in users have `CAN USE` on.
- Record its ID in the worksheet as `SQL_WAREHOUSE_ID`.

### 3.2 Unity Catalog grants
- Grant `SELECT` on `UNITY_CATALOG_TABLE` to `<user_group_app>`.
- `samples.nyctaxi.trips` is already readable by everyone in the workspace; skip this for the default value.
- For your own tables also grant `USE CATALOG` and `USE SCHEMA` along the path:
  ```sql
  GRANT USE CATALOG ON CATALOG <catalog>             TO `<user_group_app>`;
  GRANT USE SCHEMA  ON SCHEMA  <catalog>.<schema>    TO `<user_group_app>`;
  GRANT SELECT      ON TABLE   <UNITY_CATALOG_TABLE> TO `<user_group_app>`;
  ```

### 3.3 App configuration
1. **App resource** — add the SQL Warehouse to the App with key **`sql-warehouse`**. This is what `valueFrom: sql-warehouse` in `app.yaml` resolves against. The DAB block in section 4 declares this; if you are configuring through the Apps UI, add the resource manually.
2. **User-authorization scope** — add **`sql`**. Without it, `X-Forwarded-Access-Token` is not minted with SQL permissions and `sql_conn()` returns 401.

### 3.4 Claude Code prompt — provision page permissions

With the Databricks MCP server connected to Claude Code, paste the prompt below. Fill in the bracketed values from §1.1 above and from `0_initial_setup.md` §1.1.

```text
Please provision the Databricks permissions needed by the Sample Data
page described in docs/plans/1_sample_data_page.md.

Inputs from the worksheets:
- UNITY_CATALOG_TABLE: <table-fqn, default samples.nyctaxi.trips>
- SQL_WAREHOUSE_ID:    <warehouse-id>
- app_name:            <app_name from 0_initial_setup.md>
- user_group_app:      <user_group_app from 0_initial_setup.md>

Do the following, idempotently (skip if already granted), and report
each change you make:

1. Unity Catalog grants on <UNITY_CATALOG_TABLE> for <user_group_app>:
   - USE CATALOG on the catalog,
   - USE SCHEMA on the catalog.schema,
   - SELECT on the table itself.
   Use the manage_uc_grants MCP tool. Skip catalog/schema steps if the
   table is in `samples.*` since those are world-readable by default.

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

Append to the `databricks.yml` created in `0_initial_setup.md`.

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

All paths below are relative to the repo root. The page only depends on helpers already exported by `utils.py` after `0_initial_setup.md`.

### 5.1 `app.yaml`
Append two entries to `env:`:
```yaml
env:
  # SQL warehouse used by sql_conn()
  - name: SQL_WAREHOUSE_ID
    valueFrom: sql-warehouse          # Resource key declared in databricks.yml
  # Unity Catalog table to visualise
  - name: UNITY_CATALOG_TABLE
    value: "samples.nyctaxi.trips"    # Change to your three-part name
```

### 5.2 `app.py` (optional)
Splice a pointer into the existing home-page markdown so users discover the page:
```python
st.markdown(
    "- **Sample Data** — table viewer over a Unity Catalog table, "
    "queried on behalf of the signed-in user."
)
st.info("👈 Open **Sample Data** in the sidebar.")
```

### 5.3 `pages/1_Sample_Data.py`
Create this file with the full contents below.

```python
"""Sample Data - NYC taxi trips from a Unity Catalog table (OBO query)."""
import pandas as pd
import streamlit as st

from utils import get_env, render_sidebar, sql_conn

st.set_page_config(
    page_title="Sample Data",
    page_icon=":material/local_taxi:",
    layout="wide",
)
render_sidebar()

# Table FQN comes from app.yaml (trusted config, not user input).
TABLE_NAME = get_env("UNITY_CATALOG_TABLE")
ROW_LIMIT = 10_000

st.title("NYC Taxi Trips")
st.caption(
    f"Unity Catalog table `{TABLE_NAME}` — most recent {ROW_LIMIT:,} pickups, "
    f"queried on behalf of the signed-in user."
)


def load_trips(table: str, limit: int) -> pd.DataFrame:
    """Fetch a slice of trips. Table name is from trusted config (app.yaml)."""
    query = (
        f"SELECT tpep_pickup_datetime, tpep_dropoff_datetime, "
        f"trip_distance, fare_amount, pickup_zip, dropoff_zip "
        f"FROM {table} "
        f"ORDER BY tpep_pickup_datetime DESC "
        f"LIMIT {int(limit)}"
    )
    with sql_conn() as conn, conn.cursor() as cur:
        cur.execute(query)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        return df
    df["tpep_pickup_datetime"] = pd.to_datetime(df["tpep_pickup_datetime"])
    df["tpep_dropoff_datetime"] = pd.to_datetime(df["tpep_dropoff_datetime"])
    df["trip_duration_min"] = (
        df["tpep_dropoff_datetime"] - df["tpep_pickup_datetime"]
    ).dt.total_seconds() / 60.0
    return df


# Cache the dataframe per user session — avoids re-querying on every filter
# tweak. Not using st.cache_data: that cache is global across users and would
# leak data when the underlying table has row/column policies.
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

    pickup_min = df["tpep_pickup_datetime"].min().date()
    pickup_max = df["tpep_pickup_datetime"].max().date()
    date_range = st.date_input(
        "Pickup date range",
        value=(pickup_min, pickup_max),
        min_value=pickup_min,
        max_value=pickup_max,
    )

    dist_min = float(df["trip_distance"].min())
    dist_max = float(df["trip_distance"].max())
    dist_range = st.slider(
        "Trip distance (mi)",
        min_value=dist_min,
        max_value=dist_max,
        value=(dist_min, dist_max),
        step=0.1,
    )

    top_pickup_zips = (
        df["pickup_zip"].value_counts().head(20).index.astype(str).tolist()
    )
    selected_zips = st.multiselect(
        "Pickup ZIP (top 20 by trip count)",
        options=top_pickup_zips,
        default=[],
        help="Empty = all pickup ZIPs.",
    )

    st.divider()
    if st.button("Refresh data", use_container_width=True):
        st.session_state.pop("trips_df", None)
        st.rerun()

# --- Apply filters client-side ---
mask = pd.Series(True, index=df.index)

if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
    pickup_dates = df["tpep_pickup_datetime"].dt.date
    mask &= pickup_dates.between(start, end)

mask &= df["trip_distance"].between(dist_range[0], dist_range[1])

if selected_zips:
    mask &= df["pickup_zip"].astype(str).isin(selected_zips)

filtered = df.loc[mask]

# --- Headline metrics ---
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Trips", f"{len(filtered):,}")
with c2:
    avg_fare = filtered["fare_amount"].mean() if not filtered.empty else 0.0
    st.metric("Avg fare", f"${avg_fare:,.2f}")
with c3:
    avg_dist = filtered["trip_distance"].mean() if not filtered.empty else 0.0
    st.metric("Avg distance", f"{avg_dist:,.2f} mi")
with c4:
    med_dur = filtered["trip_duration_min"].median() if not filtered.empty else 0.0
    st.metric("Median duration", f"{med_dur:.1f} min")

st.divider()

st.dataframe(
    filtered,
    use_container_width=True,
    hide_index=True,
    column_config={
        "tpep_pickup_datetime": st.column_config.DatetimeColumn(
            "Pickup", format="YYYY-MM-DD HH:mm", width="medium"
        ),
        "tpep_dropoff_datetime": st.column_config.DatetimeColumn(
            "Dropoff", format="YYYY-MM-DD HH:mm", width="medium"
        ),
        "trip_distance": st.column_config.NumberColumn(
            "Distance (mi)", format="%.2f", width="small"
        ),
        "fare_amount": st.column_config.NumberColumn(
            "Fare", format="$%.2f", width="small"
        ),
        "pickup_zip": st.column_config.NumberColumn(
            "Pickup ZIP", format="%d", width="small"
        ),
        "dropoff_zip": st.column_config.NumberColumn(
            "Dropoff ZIP", format="%d", width="small"
        ),
        "trip_duration_min": st.column_config.NumberColumn(
            "Duration (min)", format="%.1f", width="small"
        ),
    },
)
```

### 5.4 Adapting to a different UC table
1. Set `UNITY_CATALOG_TABLE` in `app.yaml` to the new three-part name.
2. Replace the `SELECT` column list inside `load_trips()` with your columns. Rename the function if helpful.
3. Replace the derived-column logic (`trip_duration_min`) with anything appropriate for your data, or remove it.
4. Rewrite the sidebar filters to match your schema (enums, numeric ranges, date columns).
5. Update the headline metrics and `st.dataframe` `column_config` to match.
6. The OBO plumbing in `sql_conn()` and the session-state caching pattern do not change.

---

## Verification

1. **Static check** from the repo root:
   ```bash
   python3 -m py_compile app.py utils.py pages/1_Sample_Data.py
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
   - **Refresh data** triggers exactly one new query.
5. **OBO sanity** — sign in as a user without `SELECT` on the configured table; the page should render `st.error("Failed to query ...")` cleanly, not crash.
