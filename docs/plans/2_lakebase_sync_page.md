# Implementation Plan — Lakebase Synced Table Page (NYC Taxi)

Page-specific plan for `pages/2_Lakebase_Sync.py` — a Postgres-side view of NYC taxi data that lives in **Lakebase**, populated by a `SNAPSHOT`-mode synced table from Unity Catalog. Streamlit connects with the App service principal via psycopg, mints a fresh Lakebase OAuth token on every Postgres connection, and renders a paginated table + headline metrics.

> **Prerequisites.**
> - **`0_A_initial_setup.md`** must be done — App, `databricks.yml`, `utils.py`, `app.py`, `app.yaml`, `pyproject.toml`, `uv.lock` already in place; worksheet §1.1 values captured.
> - **`0_D_genie_setup.md`** is **required** — this plan reads from `demo.nyctaxi.v_trips_genie` (created in 0_D) and materialises it into a Delta table with a primary key for the sync.

---

## 1. Parameters to set

Page-specific knobs. App-level values (`app_name`, `user_group_app`, …) are reused from `0_A_initial_setup.md` §1.1.

| Parameter | Where it lives | Notes |
|---|---|---|
| Lakebase instance name | `databricks.yml` var `lakebase_instance_name` | DNS-safe name; hyphens OK. The bundle creates this on first deploy. In 2026+ workspaces, Databricks creates the underlying instance as Autoscale; the legacy `database_instances` schema stays backward compatible. |
| Lakebase UC catalog name | `databricks.yml` var `lakebase_catalog_name` | Postgres-style identifier — letters, digits, underscores only; **no hyphens** (Postgres reserves them). Convention: lowercase the instance name and replace `-` with `_`. |
| Sync pipeline storage catalog | `databricks.yml` var `sync_pipeline_storage_catalog` | Standard UC catalog where the sync pipeline stores checkpoints + event logs (Delta). |
| Sync pipeline storage schema | `databricks.yml` var `sync_pipeline_storage_schema` | Standard UC schema inside the storage catalog. |
| Source UC table | hard-coded in `databricks.yml` `spec.source_table_full_name` | The Delta table the sync reads from. Must have a primary key. We materialise it from the Genie view in §3.1. |
| Primary key column | `databricks.yml` `spec.primary_key_columns` | Synthetic surrogate key added during materialisation. |
| Postgres schema | `app.yaml` `SYNCED_SCHEMA` value | Schema where the sync lands in Postgres (matches the UC schema of the synced table name). |
| Postgres table | `app.yaml` `SYNCED_TABLE` value | Table name on the Postgres side. |
| App resource key | `databricks.yml` `resources.apps.<name>.resources.<name>` | The string the runtime resolves through `valueFrom:` for any Lakebase-derived env var. |
| App SP client ID | Captured **after** the first `bundle deploy` | Postgres role name granted to the App. Required for the SQL `GRANT` step in §3.4. |
| Row cap | In-code constant `ROW_LIMIT` in the page | Upper bound on rows pulled from Postgres per render. |
| Page title / icon / filename | `init_page(...)` call + filename | Streamlit-rendered. |

### 1.1 Fill-in worksheet

- **`lakebase_instance_name`** = `streamlit-demo-lakebase`
- **`lakebase_catalog_name`** = `streamlit_demo_lakebase`
- **`sync_pipeline_storage_catalog`** = `demo`
- **`sync_pipeline_storage_schema`** = `nyctaxi`
- **`source_uc_table`** = `demo.nyctaxi.trips_for_sync`
- **`primary_key_column`** = `trip_id`
- **`sync_mode`** = `SNAPSHOT`
- **`postgres_schema`** (also the UC schema portion of the synced-table name) = `nyctaxi`
- **`postgres_table`** = `trips_synced`
- **`app_resource_key`** = `lakebase-db`
- **`app_sp_client_id`** (after first deploy) = `__________________`
- **`ROW_LIMIT`** = `5000`
- **Page title** = `Lakebase Sync`
- **Page icon** = `:material/database:`
- **Page filename** = `pages/2_Lakebase_Sync.py`

---

## 2. Overview

**What the page does.** On load, opens a connection-pooled link to the Lakebase Postgres instance bound to the App, runs `SELECT * FROM <schema>.<table> ORDER BY pickup_ts DESC LIMIT <ROW_LIMIT>`, and renders the result as headline metrics + a formatted Streamlit dataframe. A "Refresh data" button clears the data cache and re-queries.

**Why a synced table.** Unity Catalog is built for analytics, Lakebase is built for transactional / interactive OLTP. The synced table copies the Delta view into a read-only Postgres replica so the app gets:

- Sub-second `SELECT … WHERE` and joins from PostgreSQL.
- Standard `pg_*` tooling (psql, drivers, ORMs) usable from the App.
- A clean separation between analytic source (Delta) and serving copy (Postgres) — Databricks recommends only read queries against synced tables.

**Why SNAPSHOT mode.** Three modes are available: `SNAPSHOT`, `TRIGGERED`, `CONTINUOUS`.

- **SNAPSHOT** — simple full-table copy on initial create + each manual / scheduled refresh. **No Change Data Feed required on the source.**
- **TRIGGERED / CONTINUOUS** — incremental, but require `ALTER TABLE … SET TBLPROPERTIES (delta.enableChangeDataFeed = true)` on the source plus more pipeline state.

`SNAPSHOT` is the lightest path for a 22 k-row demo dataset. Upgrade to `TRIGGERED` if you start seeing the page lag behind upstream edits.

**Why materialise the view first.** Synced tables require a **Delta table with a primary key**. Views cannot have PKs. The Genie-facing `demo.nyctaxi.v_trips_genie` from `0_D_genie_setup.md` is great for natural-language Q&A but not directly syncable. We add a thin shim (`demo.nyctaxi.trips_for_sync`) that is the same dataset plus a synthetic `trip_id` surrogate key.

**Why the legacy `database_instances` DAB schema in 2026+.** Databricks transparently creates new instances as Autoscale, but the DAB resource shape (`database_instances`, `database_catalogs`, `synced_database_tables`, `apps.resources.database`) stays backward compatible. The legacy shape is more declarative: the synced table is a real DAB resource, so `bundle deploy` creates it; the Autoscale-only equivalent requires a separate Python SDK bootstrap.

**End-to-end flow.**

```
demo.nyctaxi.v_trips_genie           (view from 0_D)
        │ SQL (§3.1) — one-time materialise
        ▼
demo.nyctaxi.trips_for_sync          (Delta table with PK)
        │ DAB synced_database_tables.trips_synced
        │ (SNAPSHOT pipeline created by bundle deploy)
        ▼
<lakebase_catalog_name>.nyctaxi.trips_synced
                = Postgres `nyctaxi.trips_synced` table
        │ DAB apps.<name>.resources.lakebase-db (database: binding)
        │ — injects PGHOST/PGDATABASE/PGPORT/PGSSLMODE/PGUSER
        │ — creates Postgres role for the App SP with CONNECT + CREATE
        ▼
Streamlit page: psycopg ConnectionPool, fresh OAuth token per connect()
        │ st.cache_data(ttl=60) on the result DataFrame
        ▼
Browser: headline metrics + 13-column dataframe + Refresh button
```

**Failure modes the page handles.**

- Missing `LAKEBASE_INSTANCE_NAME` env var → friendly error then `st.stop()`.
- Missing Databricks-injected `PGHOST` / `PGDATABASE` / `PGUSER` → friendly error (resource not attached).
- Query failure (auth, missing GRANT, table not yet populated) → `st.error(...)` then `st.stop()`.
- Empty result (snapshot pipeline hasn't run yet) → `st.info(...)` with hint to trigger a refresh.

---

## 3. Databricks-side prerequisites

### 3.1 Materialise the curated view into a syncable table

Synced tables need a Delta source with a primary-key constraint. Run these three statements in the SQL editor (or via the Databricks MCP `execute_sql` tool) on any Pro/Serverless warehouse:

```sql
-- 1) Materialise the Genie view, adding a synthetic primary key.
CREATE OR REPLACE TABLE demo.nyctaxi.trips_for_sync
COMMENT 'Materialised copy of demo.nyctaxi.v_trips_genie with a synthetic primary key, used as the source for the Lakebase synced table nyctaxi.trips_synced.'
AS
SELECT
  ROW_NUMBER() OVER (ORDER BY pickup_ts, pickup_zip, dropoff_zip) AS trip_id,
  pickup_ts, dropoff_ts,
  pickup_zip, dropoff_zip, route,
  trip_distance_miles, fare_amount_usd,
  duration_minutes, fare_per_mile,
  pickup_day_of_week, time_of_day, valid_trip
FROM demo.nyctaxi.v_trips_genie;

-- 2) Primary keys require NOT NULL columns.
ALTER TABLE demo.nyctaxi.trips_for_sync
  ALTER COLUMN trip_id SET NOT NULL;

-- 3) Declare the PK constraint — this is what synced_database_tables looks for.
ALTER TABLE demo.nyctaxi.trips_for_sync
  ADD CONSTRAINT trips_for_sync_pk PRIMARY KEY (trip_id);
```

Idempotent: re-running 1 replaces the table and re-issues 2 / 3.

### 3.2 First `bundle deploy`

After §4 + §5 below are in place:

```bash
databricks bundle validate -t dev
databricks bundle deploy  -t dev
databricks bundle run streamlit-demo -t dev
```

`deploy` creates (in order, thanks to the Terraform dependency edges in §4.2):

1. The Lakebase instance.
2. The UC catalog registering the instance.
3. The SNAPSHOT synced table pipeline — and the initial snapshot runs automatically.
4. The App resource binding to the database — Databricks creates a Postgres role for the App SP with `CONNECT` + `CREATE`, and injects `PGHOST` / `PGDATABASE` / `PGPORT` / `PGSSLMODE` / `PGUSER` into the App at runtime.

**The role exists at the Postgres level but has no table grants yet.** Without §3.3–§3.4, the page will return *"permission denied for table trips_synced"*.

### 3.3 Provision the Postgres role *(one-off, after first deploy)*

The App's Postgres role is created lazily: it appears the first time the App actually connects. Two paths:

- **Just open the page once.** The Streamlit code triggers a `WorkspaceClient().database.generate_database_credential(...)` and a connect attempt, which creates the role server-side. The page will show *"permission denied for table"* — that's expected; move on to §3.4.
- **Manual trigger** (skip if you opened the page): `databricks bundle run streamlit-demo -t dev` already starts the app; the role appears when any session hits the database.

### 3.4 Grant table access in Lakebase

This is the only step that the bundle cannot automate today. Follow the runbook:

**Step 1 — Find the App SP client ID**

```bash
databricks apps get <app_name> --output JSON | jq -r '.service_principal_client_id'
```

Replace `<app_name>` with the value from `databricks.yml` (the `name:` field under `resources.apps.streamlit-demo`, **not** the YAML key). Record the resulting UUID in §1.1 as `app_sp_client_id`.

**Step 2 — Run GRANTs in the Lakebase SQL editor**

Open **Lakebase → projects → <project-id> → branches → <branch> → tables** in the Databricks workspace and switch to the SQL editor. Execute, with the placeholders filled in:

```sql
-- Confirm the role exists (visit the app once first if this returns 0 rows):
SELECT rolname FROM pg_roles WHERE rolname = '<app_sp_client_id>';

-- Grant the minimum needed for SELECT through the schema.
GRANT USAGE  ON SCHEMA nyctaxi              TO "<app_sp_client_id>";
GRANT SELECT ON TABLE  nyctaxi.trips_synced TO "<app_sp_client_id>";

-- Verify (both should return `t`).
SELECT has_schema_privilege('<app_sp_client_id>', 'nyctaxi',                'USAGE');
SELECT has_table_privilege ('<app_sp_client_id>', 'nyctaxi.trips_synced',   'SELECT');
```

No app restart is needed — Postgres applies grants immediately.

**Troubleshooting**

- `pg_roles` returns no rows → the app hasn't connected yet. Open the app URL once, then retry.
- `GRANT` errors with `permission denied` → check schema ownership with `SELECT schema_owner FROM information_schema.schemata WHERE schema_name = 'nyctaxi';` and run the GRANT as that owner.
- The page still shows *"permission denied for table"* after grants succeed → check you're granting to the **role name == App SP client ID** with double-quotes (UUIDs are case-sensitive identifiers in Postgres).

### 3.5 Claude Code prompt — automate §3.1 + the §3.4 lookup

Paste this into Claude Code with the Databricks MCP server attached. It runs §3.1 idempotently, captures the SP client ID, and prints the GRANT SQL ready to paste into Lakebase.

```text
Provision the SQL bits for the Lakebase Synced Table page described in
docs/plans/1_B_lakebase_sync_page.md.

Inputs from §1.1 + 0_A_initial_setup.md §1.1:
- app_name:                       <app_name from databricks.yml resources.apps.streamlit-demo.name>
- sql_warehouse_id:               <warehouse-id with USE CATALOG / CREATE TABLE on demo>
- source_uc_table:                demo.nyctaxi.trips_for_sync
- postgres_schema:                nyctaxi
- postgres_table:                 trips_synced

Do the following idempotently and report each change:

1. Run the three SQL statements from §3.1 of the plan to (re)create
   demo.nyctaxi.trips_for_sync from demo.nyctaxi.v_trips_genie with the
   trip_id surrogate primary key. Use the warehouse above. Use
   CREATE OR REPLACE TABLE so re-runs are safe.

2. Get the App service-principal client ID by running:
     databricks apps get <app_name> --output JSON
   and extracting `service_principal_client_id`. Print it so I can paste
   it into the Lakebase SQL editor.

3. Print the exact SQL block from §3.4 with <app_sp_client_id>
   substituted. Tell me to paste it into the SQL editor at:
     Lakebase → projects → <project-id> → branches → <branch> → tables
   No app restart is needed after the GRANTs.

Do NOT attempt to run the Postgres GRANTs yourself — the MCP layer cannot
authenticate to Lakebase Postgres.
```

---

## 4. DAB updates

Append to `databricks.yml` from `0_A_initial_setup.md`. The four blocks below add the Lakebase instance, UC catalog registration, synced-table pipeline, and the App's `database:` binding.

### 4.1 New variables

```yaml
variables:
  # ... existing variables ...
  lakebase_instance_name:
    description: "Lakebase Provisioned database instance name (DNS-safe, hyphens OK)."
  lakebase_catalog_name:
    description: "UC catalog name that registers the Lakebase instance (underscores, no hyphens)."
  sync_pipeline_storage_catalog:
    description: "Standard UC catalog where the sync pipeline stores checkpoints + event logs."
    default: demo
  sync_pipeline_storage_schema:
    description: "Standard UC schema for the sync pipeline storage."
    default: nyctaxi
```

### 4.2 Lakebase resources + App binding

Append under `resources:` *(NOT inside `resources.apps`)*:

```yaml
resources:
  # Lakebase database instance (legacy `database_instances` schema).
  database_instances:
    lakebase:
      name: ${var.lakebase_instance_name}
      capacity: CU_1

  # UC catalog that registers the Lakebase database so synced tables can land in UC.
  database_catalogs:
    lakebase_catalog:
      name: ${var.lakebase_catalog_name}
      database_instance_name: ${resources.database_instances.lakebase.name}
      database_name: databricks_postgres
      create_database_if_not_exists: true

  # SNAPSHOT-mode sync from the UC source table → Lakebase Postgres.
  #
  # IMPORTANT: `name` references resources.database_catalogs.lakebase_catalog.name
  # rather than var.lakebase_catalog_name. Both produce the same string, but the
  # resource reference creates a Terraform dependency edge so the catalog is
  # created BEFORE the synced table. Without it, Terraform parallelises both and
  # the synced table fails with "Catalog '<name>' does not exist".
  synced_database_tables:
    trips_synced:
      name: ${resources.database_catalogs.lakebase_catalog.name}.nyctaxi.trips_synced
      database_instance_name: ${resources.database_instances.lakebase.name}
      logical_database_name: databricks_postgres
      spec:
        source_table_full_name: demo.nyctaxi.trips_for_sync
        primary_key_columns:
          - trip_id
        scheduling_policy: SNAPSHOT
        create_database_objects_if_missing: true
        new_pipeline_spec:
          storage_catalog: ${var.sync_pipeline_storage_catalog}
          storage_schema: ${var.sync_pipeline_storage_schema}
```

And append the App binding under `resources.apps.streamlit-demo.resources`:

```yaml
resources:
  apps:
    streamlit-demo:
      # ... existing config ...
      resources:
        # ... existing entries (e.g. sql-warehouse if you have the Sample Data page) ...
        - name: lakebase-db
          database:
            instance_name: ${resources.database_instances.lakebase.name}
            database_name: databricks_postgres
            permission: CAN_CONNECT_AND_CREATE
```

### 4.3 Target values

```yaml
targets:
  dev:
    variables:
      # ... existing ...
      lakebase_instance_name: "streamlit-demo-lakebase"
      lakebase_catalog_name: "streamlit_demo_lakebase"
      sync_pipeline_storage_catalog: "demo"
      sync_pipeline_storage_schema: "nyctaxi"
```

### 4.4 Validate + deploy

```bash
databricks bundle validate -t dev
databricks bundle deploy  -t dev
databricks bundle run streamlit-demo -t dev
```

Then complete §3.3 (visit the app once to materialise the Postgres role) and §3.4 (GRANT in the Lakebase SQL editor). Page works after that.

---

## 5. Source code updates

### 5.1 `pyproject.toml`

Add the Postgres driver and its pool helper. `[binary]` brings the precompiled wheel (avoids a libpq build step); `[pool]` adds `psycopg_pool.ConnectionPool`.

```toml
dependencies = [
    "streamlit>=1.57.0",
    "pandas>=2.3.3",
    "databricks-sql-connector>=4.2.6",
    "databricks-sdk>=0.108.0",
    "psycopg[binary,pool]>=3.2",
]
```

Refresh the lockfile:

```bash
uv lock
```

### 5.2 `app.yaml`

Append to `env:`:

```yaml
env:
  # ... existing entries ...

  # Lakebase synced-table page. PGHOST / PGDATABASE / PGPORT / PGSSLMODE / PGUSER
  # are auto-injected by Databricks Apps when the `lakebase-db` resource is bound.
  - name: LAKEBASE_INSTANCE_NAME
    value: "streamlit-demo-lakebase"      # Must match databricks.yml var.lakebase_instance_name
  - name: SYNCED_SCHEMA
    value: "nyctaxi"
  - name: SYNCED_TABLE
    value: "trips_synced"
```

> `LAKEBASE_INSTANCE_NAME` is a literal `value:` rather than `valueFrom:`. The instance name is static per environment; using a literal avoids a second indirection step.

### 5.3 `pages/2_Lakebase_Sync.py`

Create this file with the full contents below. Reads the synced Postgres table with a connection pool that mints a fresh OAuth token on every new connection — so long-lived deployments never see expired credentials (Provisioned Lakebase tokens last ~1 hour).

```python
"""Lakebase Sync — query the synced NYC taxi trips table over Postgres.

Reads from the Lakebase-side replica of demo.nyctaxi.trips_for_sync which
was synced from Unity Catalog via the synced_database_tables DAB resource
(see databricks.yml). Connects with the app service principal: a fresh OAuth
token is minted on every Postgres connect() so long-lived pools never see
an expired credential.
"""
import os
import uuid

import pandas as pd
import psycopg
import streamlit as st
from databricks.sdk import WorkspaceClient
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from utils import init_page

init_page(page_title="Lakebase Sync", page_icon=":material/database:")

# Env vars injected by app.yaml / Databricks Apps resource binding.
INSTANCE_NAME = os.environ.get("LAKEBASE_INSTANCE_NAME", "")
SCHEMA_NAME = os.environ.get("SYNCED_SCHEMA", "nyctaxi")
TABLE_NAME = os.environ.get("SYNCED_TABLE", "trips_synced")
ROW_LIMIT = 5_000

st.title("NYC Taxi Trips — Lakebase Synced")
st.caption(
    f"Postgres view of `{SCHEMA_NAME}.{TABLE_NAME}` in Lakebase instance "
    f"`{INSTANCE_NAME}`, synced from `demo.nyctaxi.trips_for_sync` in Unity Catalog."
)

if not INSTANCE_NAME:
    st.error(
        "`LAKEBASE_INSTANCE_NAME` is not set. Check `app.yaml` and confirm the "
        "`lakebase-db` resource is bound to the app."
    )
    st.stop()


class LakebaseOAuthConnection(psycopg.Connection):
    """Mint a fresh Lakebase OAuth token on every Postgres connect.

    Provisioned tokens expire after ~1 hour, so this avoids stale-credential
    failures on long-lived pools. The token is passed as the Postgres password.
    """

    @classmethod
    def connect(cls, conninfo: str = "", **kwargs):
        w = WorkspaceClient()
        credential = w.database.generate_database_credential(
            request_id=str(uuid.uuid4()),
            instance_names=[INSTANCE_NAME],
        )
        kwargs["password"] = credential.token
        return super().connect(conninfo, **kwargs)


@st.cache_resource
def get_pool() -> ConnectionPool:
    required = ("PGHOST", "PGDATABASE", "PGUSER")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Missing Databricks-injected env vars: "
            + ", ".join(missing)
            + ". Confirm the `lakebase-db` resource is attached in databricks.yml."
        )
    conninfo = (
        f"host={os.environ['PGHOST']} "
        f"port={os.environ.get('PGPORT', '5432')} "
        f"dbname={os.environ['PGDATABASE']} "
        f"user={os.environ['PGUSER']} "
        f"sslmode={os.environ.get('PGSSLMODE', 'require')}"
    )
    return ConnectionPool(
        conninfo=conninfo,
        connection_class=LakebaseOAuthConnection,
        min_size=0,
        max_size=5,
        max_lifetime=1800,   # 30 min — well under the 1 hr token lifetime
        open=True,
    )


@st.cache_data(ttl=60)
def fetch_trips(schema: str, table: str, limit: int) -> pd.DataFrame:
    """Read the latest `limit` rows from the synced table.

    Safe to share across users: the synced table is read-only and queried
    with the app SP credential, so every viewer sees identical data.
    """
    query = sql.SQL(
        "SELECT * FROM {schema}.{table} ORDER BY pickup_ts DESC LIMIT %s"
    ).format(
        schema=sql.Identifier(schema),
        table=sql.Identifier(table),
    )
    with get_pool().connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, (limit,))
        return pd.DataFrame(cur.fetchall())


try:
    df = fetch_trips(SCHEMA_NAME, TABLE_NAME, ROW_LIMIT)
except Exception as exc:
    st.error(f"Failed to query Lakebase: {exc}")
    st.stop()

if df.empty:
    st.info(
        "No rows in the synced table yet. SNAPSHOT pipelines run on first create "
        "and on each scheduled refresh — trigger one from the Databricks UI "
        "or wait for the next run."
    )
    st.stop()

# --- Headline metrics --------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Rows", f"{len(df):,}")
if "fare_amount_usd" in df.columns:
    c2.metric("Avg fare", f"${df['fare_amount_usd'].mean():,.2f}")
if "trip_distance_miles" in df.columns:
    c3.metric("Avg distance", f"{df['trip_distance_miles'].mean():,.2f} mi")
if "duration_minutes" in df.columns:
    c4.metric("Median duration", f"{df['duration_minutes'].median():.1f} min")

st.divider()

st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "trip_id": st.column_config.NumberColumn("ID", format="%d", width="small"),
        "pickup_ts": st.column_config.DatetimeColumn("Pickup", format="YYYY-MM-DD HH:mm", width="medium"),
        "dropoff_ts": st.column_config.DatetimeColumn("Dropoff", format="YYYY-MM-DD HH:mm", width="medium"),
        "pickup_zip": st.column_config.TextColumn("Pickup ZIP", width="small"),
        "dropoff_zip": st.column_config.TextColumn("Dropoff ZIP", width="small"),
        "route": st.column_config.TextColumn("Route", width="small"),
        "trip_distance_miles": st.column_config.NumberColumn("Distance (mi)", format="%.2f", width="small"),
        "fare_amount_usd": st.column_config.NumberColumn("Fare", format="$%.2f", width="small"),
        "duration_minutes": st.column_config.NumberColumn("Duration (min)", format="%.1f", width="small"),
        "fare_per_mile": st.column_config.NumberColumn("Fare/mi", format="$%.2f", width="small"),
        "pickup_day_of_week": st.column_config.TextColumn("Day", width="small"),
        "time_of_day": st.column_config.TextColumn("Time of day", width="small"),
        "valid_trip": st.column_config.CheckboxColumn("Valid", width="small"),
    },
)

if st.button("Refresh data", use_container_width=False):
    st.cache_data.clear()
    st.rerun()
```

Key choices to be aware of:

- **`st.cache_data` is safe here** even though it's process-global. All users query as the same App SP, so there's no OBO-flavoured row leakage to worry about. (Contrast with the Sample Data page, where queries run OBO and we use `st.session_state` instead.)
- **`max_lifetime=1800`** is the trick that keeps long-lived deployments alive. The connection class mints a fresh token on each connect, but the pool reuses connections; capping lifetime at 30 min ensures stale tokens never hit the wire.
- **The `LakebaseOAuthConnection` subclass overrides `connect()`** — this is the documented psycopg pattern for injecting a per-connection password. The pool calls `connection_class.connect(...)` directly when it needs a new connection.

### 5.4 Adapting to a different synced table

Most swaps stay inside `app.yaml` + the DAB spec.

1. **Different source table**: update `databricks.yml` `synced_database_tables.trips_synced.spec.source_table_full_name` to your three-part name, and `primary_key_columns` to the source's PK column(s). Either ensure the source already has a PK declared, or apply §3.1's `ALTER TABLE … ADD CONSTRAINT … PRIMARY KEY` to your table.
2. **Different Postgres schema / table**: update both `app.yaml` (`SYNCED_SCHEMA` / `SYNCED_TABLE`) **and** the third part of `synced_database_tables.trips_synced.name` in `databricks.yml` so they match. Re-run §3.4 with the new schema / table names.
3. **Different columns**: the page's `column_config` keys are tolerant of missing columns (Streamlit ignores keys that don't appear in the DataFrame), but you'll lose pretty formatting on new columns. Add an entry for each one.
4. **TRIGGERED / CONTINUOUS mode**: enable CDF on the source first:
   ```sql
   ALTER TABLE demo.nyctaxi.trips_for_sync
     SET TBLPROPERTIES (delta.enableChangeDataFeed = true);
   ```
   …then switch `scheduling_policy: TRIGGERED` (and optionally add a `jobs:` resource that runs the pipeline on a cron) or `scheduling_policy: CONTINUOUS`. SNAPSHOT does not require CDF.

---

## Verification

1. **Static check** from the repo root:
   ```bash
   uv sync
   uv run python -m py_compile app.py utils.py pages/2_Lakebase_Sync.py
   ```
2. **Bundle validate**:
   ```bash
   databricks bundle validate -t dev
   ```
3. **Deploy + run**:
   ```bash
   databricks bundle deploy -t dev
   databricks bundle run streamlit-demo -t dev
   ```
4. **Smoke test in browser**
   - Open the app → **Lakebase Sync** tab. Expected first time: *"permission denied for table trips_synced"* (the App SP role exists but has no GRANTs yet). This is the cue that the Postgres role has been provisioned.
   - Complete §3.4 in the Lakebase SQL editor.
   - Refresh the page → headline metrics + ~5,000 rows of taxi data render.
   - Click **Refresh data** → data cache clears, page re-queries, same data back (the snapshot is static).
5. **Token-rotation sanity**
   - Leave the page open for 90 minutes (longer than the 1 hr token lifetime).
   - Click **Refresh data**. If the page renders, the pool's `max_lifetime=1800` and per-connect token logic are working. If you see *"connection authentication failed"*, the pool kept a stale connection — verify `max_lifetime` is set on the `ConnectionPool` constructor.

---

## What to avoid

- **Trying to sync a view directly.** `synced_database_tables` needs a Delta **table** with a primary key. Views have neither — materialise first.
- **Using `${var.lakebase_catalog_name}` inside `synced_database_tables.<name>.name`.** It produces the same string as `${resources.database_catalogs.lakebase_catalog.name}` but Terraform won't infer the catalog dependency from a variable. Both resources will race in parallel; the synced table loses with *"Catalog '<name>' does not exist."* See §4.2 — the resource reference is load-bearing.
- **Caching the connection itself.** Provisioned Lakebase OAuth tokens expire after ~1 hour. A single long-lived `psycopg.connect()` will start failing as soon as the token expires. Use the pool + `LakebaseOAuthConnection` pattern so each connect gets a fresh token, and cap `max_lifetime` to recycle connections before the token does.
- **Hyphens in `lakebase_catalog_name`.** Postgres treats hyphens as operators, so any unquoted identifier with a `-` fails to parse. Use underscores for the UC catalog name even if the Lakebase instance name has hyphens.
- **Forgetting that bundle `destroy` deletes the data.** `databricks bundle destroy -t dev` tears down the Lakebase instance — which removes the synced Postgres table and any Postgres-side state. Only run it when you really want a clean slate.
- **Expecting the bundle to issue the Postgres GRANT.** The DAB `database:` binding gives the App SP `CONNECT` + `CREATE` on the database but no table grants. §3.4's GRANT step is mandatory and one-time per (role, table) pair.
