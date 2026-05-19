# Implementation Plan — Genie Space for NYC Taxi (curated `demo` catalog)

Provisioning plan for a Databricks Genie Space backed by a curated copy of `samples.nyctaxi.trips`. Produces a working `NYC Taxi Trips Genie` space that downstream Streamlit pages (or any Genie consumer) can talk to. App-side integration is **not** in scope here — that lands in a per-page plan.

> **Prerequisite.** Complete `0_A_initial_setup.md` first — this plan assumes `databricks.yml`, the App, and the deploy SP (or your user) have workspace access. Brand-agnostic; does not depend on `0_B_design_system.md`.

> **Source-of-truth principle.** Don't point Genie at `samples.nyctaxi.trips` directly: the `samples` catalog is read-only, so you can't attach UC comments, statistics, synonyms, or SQL expressions to it. Instead clone it into a writable catalog (`demo.nyctaxi.trips_raw`), build one curated business-facing view (`demo.nyctaxi.v_trips_genie`) and attach **only the view** to Genie. The raw table stays around for ad-hoc query and audit, but Genie never sees it directly.

> **DAB-first.** The repo's `databricks.yml` now owns the schema (`demo_${monogram}.nyctaxi`) and the source-table comments via a `resources.schemas` block with grants. Tables and views (`trips_raw`, `v_trips_genie`, `trips_for_sync`) live in `scripts/bootstrap.py` because DAB has no `tables` / `views` resource type today. The **Genie Space itself is still created manually** — Agent Bricks artefacts are not in the bundle schema yet. The imperative `manage_uc_objects` + `execute_sql` path in §3.2 / §3.3 / §3.4 below remains documented as an **optional alternative** for workspaces without DAB tooling.

> **Naming convention — shared catalog, monogrammed schema.** Every resource this plan creates lives inside the **shared `demo` catalog** (pre-existing). The *schema* carries the developer's monogram (see `0_A_initial_setup.md` §1.0 — derived from `databricks current-user me` → `displayName`). Use `demo.nyctaxi_${monogram}` (shared catalog + monogrammed schema) and `NYC Taxi Trips Genie (${monogram})` for the Genie display name. **All `demo.nyctaxi.…` literals in the SQL / YAML / CLI snippets below are placeholders — substitute `demo.nyctaxi_${monogram}.…` everywhere when running for real.** Two developers on the same workspace can run this plan side-by-side without collisions as long as their monograms differ.
>
> **No `CREATE CATALOG` required.** This plan never creates a catalog — the shared `demo` catalog is provisioned once by a metastore admin and every operator carves a personal schema inside it. If you do not have `CREATE CATALOG ON METASTORE`, the default path works for you as-is.

---

## 1. Parameters to set

Page-agnostic; all knobs live in Unity Catalog or on the Genie Space itself.

| Parameter | Where it lives | Notes |
|---|---|---|
| Catalog name | Unity Catalog | **Shared `demo` catalog — pre-existing.** Operators only need `USE CATALOG` + `CREATE SCHEMA` on it. No `CREATE CATALOG` required. |
| Schema name | Unity Catalog | Per-operator schema (monogrammed) — holds the raw clone + curated view. Operator owns and can drop it without touching shared resources. |
| Raw table name | Unity Catalog | Deep clone of `samples.nyctaxi.trips`; not attached to Genie. |
| Curated view name | Unity Catalog | The only object attached to Genie. Renames + derives columns for readability. |
| SQL warehouse ID | Genie Space settings | Must be Pro or Serverless — Genie does not support Classic warehouses. |
| Genie Space display name | Genie Space settings | Shown in the Spaces list. |
| Genie Space ID | Captured after `create_or_update_genie` returns | Use this as the `space_id` in the bundle binding + Streamlit chat page. |
| App resource key | `databricks.yml` (see §4) | The string under `resources.apps.<name>.resources.<name>` and the `valueFrom:` target in `app.yaml`. |
| User group(s) | Genie Space sharing + UC grants | End users need `CAN RUN` on the space and `SELECT` on the view. |

### 1.1 Fill-in worksheet

- **`catalog_name`** = `demo` *(shared — do not create)*
- **`schema_name`** = `nyctaxi_${monogram}` *(per-operator, monogrammed)*
- **`raw_table`** = `trips_raw` *(full name `demo.nyctaxi_${monogram}.trips_raw`)*
- **`curated_view`** = `v_trips_genie` *(full name `demo.nyctaxi_${monogram}.v_trips_genie`)*
- **`source_table`** = `samples.nyctaxi.trips`
- **`sql_warehouse_id`** = `__________________` *(must be Pro or Serverless)*
- **`genie_space_name`** = `NYC Taxi Trips Genie`
- **`genie_space_id`** (captured after creation, e.g. `01f152305d531fc9b1c8e70b439bfa9e`) = `__________________`
- **`app_resource_key`** = `genie-space`
- **`user_group_app`** (from `0_A_initial_setup.md`) = `__________________`

---

## 2. Overview

**What the plan produces.** A four-object Unity Catalog stack plus one Genie Space (the `demo` catalog itself is shared and pre-existing — operators never create it):

```
demo                               ← catalog (shared, pre-existing)
└── nyctaxi_${monogram}            ← schema (operator-owned, monogrammed)
    ├── trips_raw                  ← deep clone of samples.nyctaxi.trips (audit / ad-hoc)
    └── v_trips_genie              ← curated view: friendly columns, derived buckets,
                                     valid_trip filter, comments on every column
                                     ↑ the only object attached to the Genie Space

NYC Taxi Trips Genie               ← Genie Space (id captured at creation)
  └── attached: demo.nyctaxi.v_trips_genie
  └── 8 sample questions, dataset-range-aware description
  └── synonyms / SQL expressions / example SQL / benchmarks   (§3.7, UI work)
```

**Why a curated view.** Three reasons:

1. **Business vocabulary.** `tpep_pickup_datetime` becomes `pickup_ts`; `fare_amount` becomes `fare_amount_usd`; ZIPs become strings; we add `route`, `duration_minutes`, `fare_per_mile`, `time_of_day`, `pickup_day_of_week`, `valid_trip`. Genie's prompt-matching works on column names — friendly names dramatically improve answer quality.
2. **One way to compute things.** With raw + view both attached, Genie picks whichever; answers drift. One curated object = one canonical answer shape.
3. **Quality filter baked in.** `valid_trip` flags trips with positive distance, fare, and duration. Text instructions (§3.7.3) tell Genie to filter on this for fare/distance/duration analysis.

**Dataset realities to remember.**

- Date range is **2016-01-01 → 2016-02-29**. `CURRENT_DATE`-relative filters return nothing — text instructions explicitly forbid them.
- 21,932 rows total, 21,770 valid. Small enough to expose without sampling, large enough to behave like real data.
- Fare = metered `fare_amount` only — no tips, tolls, taxes, or `total_amount`. The Genie description spells this out so users don't ask for things that aren't there.

**End-to-end flow.**

1. **Schema** — `manage_uc_objects` (MCP) or `CREATE SCHEMA` (admin UI). The `demo` catalog is shared and pre-existing — only the per-operator schema (`demo.nyctaxi_${monogram}`) is created here.
2. **Raw clone + comments** — `CREATE TABLE IF NOT EXISTS … DEEP CLONE`, then `ANALYZE TABLE`, then `COMMENT ON` + `ALTER TABLE … ALTER COLUMN … COMMENT`.
3. **Curated view** — single `CREATE OR REPLACE VIEW` with per-column comments.
4. **Profile validation** — one query confirming row counts and date range, plus the suspicious-records counters.
5. **Genie Space basics** — `create_or_update_genie` (MCP), or *New Genie Space* in the UI: attach the view, set name, description, warehouse, sample questions.
6. **Deeper Genie config** — synonyms, prompt matching, text instructions, SQL expressions, example SQL, parameterised examples, benchmarks. This part is **UI-only today** (or via `serialized_space` JSON); the MCP `create_or_update_genie` tool does not expose these fields directly. The Claude Code prompt in §3.8 walks the reader through it.
7. **Share + monitor** — grant `CAN RUN` / `SELECT`, then iterate using Genie's Monitor tab and the benchmarks.

---

## 3. Databricks-side prerequisites and setup

> **Recommended path:** `databricks bundle deploy -t dev` creates the schemas + grants; `uv run python scripts/bootstrap.py` creates the tables, view, and PDF uploads; `manage_genie` / the UI creates the Genie Space itself. Skip §3.2 (catalog/schema), §3.3, §3.4, §3.5 below if you go this route — they are kept for the imperative-only fallback. §3.6 (create Genie Space) and §3.7 (UI configuration) are still **mandatory** because DAB does not own those.

### 3.0 DAB-first (recommended)

What the bundle owns:

```yaml
resources:
  schemas:
    nyctaxi:
      catalog_name: demo                 # shared catalog — DAB does NOT create it
      name: nyctaxi_${workspace.current_user.short_name}
      comment: NYC taxi sample data curated for Genie + Streamlit feature pages.
      grants:
        - principal: ${var.app_sp_client_id}
          privileges: [USE_SCHEMA, SELECT]
```

What `scripts/bootstrap.py` owns (run once after `bundle deploy`):

1. `CREATE TABLE IF NOT EXISTS demo.nyctaxi.trips_raw DEEP CLONE samples.nyctaxi.trips`
2. `ANALYZE TABLE … COMPUTE STATISTICS FOR ALL COLUMNS`
3. Table + column comments on `trips_raw`
4. `CREATE OR REPLACE VIEW demo.nyctaxi.v_trips_genie …`
5. `CREATE OR REPLACE TABLE demo.nyctaxi.trips_for_sync …` + NOT NULL + PRIMARY KEY constraint
6. `GRANT SELECT ON VIEW demo.nyctaxi.v_trips_genie TO <app_sp>`

Run order from a fresh workspace:

```bash
# 1. The `demo` catalog is shared and pre-existing — DO NOT create it.
#    Confirm it exists and that you have USE CATALOG + CREATE SCHEMA on it.
#    If `demo` is missing, ask the metastore admin to provision it once
#    (NOT required of operators — it's a one-time platform setup).
# 2. Deploy the bundle (creates your per-operator schema with grants):
databricks bundle deploy -t dev
# 3. Bootstrap tables + view + PDFs:
uv run python scripts/bootstrap.py \
    --warehouse-id "$DATABRICKS_WAREHOUSE_ID" \
    --app-sp-client-id "$DATABRICKS_APP_SP_CLIENT_ID"
# 4. Create the Genie Space (still manual — see §3.6 / §3.8 below).
```

The §3.2 / §3.3 / §3.4 / §3.5 sections below are the imperative-only fallback (no DAB tooling available).

### 3.1 Required privileges and resources

- `USE CATALOG` + `CREATE SCHEMA` on the shared `demo` catalog. **`CREATE CATALOG` on the metastore is NOT required** — the runbook deliberately uses the existing shared `demo` catalog. If `demo` does not exist in your workspace, request a one-time metastore admin to create it; never request `CREATE CATALOG` for the operator group.
- `SELECT` on `samples.nyctaxi.trips` — public by default; nothing to do.
- A running SQL Warehouse with `warehouse_type = PRO` (or Serverless). **Classic warehouses are not supported by Genie.** Run `databricks warehouses list` and pick one; record the ID in §1.1.
- For end users of the space: workspace access + the SQL warehouse `CAN_USE` + Genie Space `CAN_RUN` + UC `SELECT` on the view (and `USE CATALOG demo` / `USE SCHEMA demo.nyctaxi`).

### 3.2 Phase 1 — Schema *(optional / fallback — DAB owns the schema in §3.0)*

The `demo` catalog is **shared and pre-existing** — do not create it. This step only carves the operator's personal schema inside it.

If you have the Databricks MCP server attached to Claude Code, this is one MCP call:

```text
manage_uc_objects(object_type="schema",  action="create", name="nyctaxi_${monogram}", catalog_name="demo", comment="NYC taxi sample data curated for Genie + Streamlit feature pages.")
```

CLI fallback (run as a user with `CREATE SCHEMA` on `demo`):

```bash
databricks schemas create --name nyctaxi_${monogram} --catalog-name demo \
  --comment "NYC taxi sample data curated for Genie + Streamlit feature pages."
```

> **Do not run `databricks catalogs create --name demo`.** This runbook intentionally treats `demo` as shared infrastructure. Operators only need `USE CATALOG` + `CREATE SCHEMA` on it. If `demo` truly doesn't exist, escalate once to the metastore admin rather than granting `CREATE_CATALOG` to the operator group.

### 3.3 Phase 2 — Raw clone, statistics, comments

Run these as separate statements via the SQL editor, `databricks sql query`, or MCP `execute_sql` against your Pro/Serverless warehouse. They are idempotent: re-running just refreshes statistics and rebinds comments.

```sql
CREATE TABLE IF NOT EXISTS demo.nyctaxi.trips_raw
  DEEP CLONE samples.nyctaxi.trips;

ANALYZE TABLE demo.nyctaxi.trips_raw COMPUTE STATISTICS FOR ALL COLUMNS;

COMMENT ON TABLE demo.nyctaxi.trips_raw IS
  'NYC taxi trip records cloned from samples.nyctaxi.trips. One row represents one taxi trip.';

ALTER TABLE demo.nyctaxi.trips_raw ALTER COLUMN tpep_pickup_datetime
  COMMENT 'Trip pickup timestamp. Use this as the default time dimension for trip analysis.';
ALTER TABLE demo.nyctaxi.trips_raw ALTER COLUMN tpep_dropoff_datetime
  COMMENT 'Trip dropoff timestamp. Use only when users ask about dropoff time or trip duration.';
ALTER TABLE demo.nyctaxi.trips_raw ALTER COLUMN trip_distance
  COMMENT 'Trip distance in miles.';
ALTER TABLE demo.nyctaxi.trips_raw ALTER COLUMN fare_amount
  COMMENT 'Metered fare amount in USD. Excludes tips, tolls, taxes, and surcharges.';
ALTER TABLE demo.nyctaxi.trips_raw ALTER COLUMN pickup_zip
  COMMENT 'ZIP code where the taxi trip started.';
ALTER TABLE demo.nyctaxi.trips_raw ALTER COLUMN dropoff_zip
  COMMENT 'ZIP code where the taxi trip ended.';
```

> **Quirk.** The MCP `execute_sql` tool errors on `CREATE OR REPLACE TABLE … DEEP CLONE` but accepts `CREATE TABLE IF NOT EXISTS … DEEP CLONE`. Use the latter form when scripting through MCP; both are equivalent for a first-time create.

### 3.4 Phase 3 — Curated Genie-facing view

One statement; replaces in place on re-run.

```sql
CREATE OR REPLACE VIEW demo.nyctaxi.v_trips_genie
(
  pickup_ts            COMMENT 'Taxi pickup timestamp. Default timestamp for time-based trip analysis.',
  dropoff_ts           COMMENT 'Taxi dropoff timestamp.',
  pickup_date          COMMENT 'Calendar date of pickup.',
  pickup_month         COMMENT 'Calendar month of pickup.',
  pickup_hour          COMMENT 'Hour of pickup from 0 to 23.',
  pickup_day_of_week   COMMENT 'Day of week name derived from pickup timestamp.',
  pickup_day_number    COMMENT 'Day-of-week number where 1 = Sunday and 7 = Saturday.',
  time_of_day          COMMENT 'Business time-of-day bucket: Morning, Afternoon, Evening, or Night.',
  trip_distance_miles  COMMENT 'Trip distance in miles.',
  fare_amount_usd      COMMENT 'Metered fare in USD. Excludes tips, tolls, taxes, and surcharges.',
  pickup_zip           COMMENT 'Pickup ZIP code as text.',
  dropoff_zip          COMMENT 'Dropoff ZIP code as text.',
  route                COMMENT 'Pickup-to-dropoff route represented as pickup_zip-dropoff_zip.',
  duration_minutes     COMMENT 'Trip duration in minutes.',
  fare_per_mile        COMMENT 'Trip-level fare per mile, calculated as fare_amount_usd / trip_distance_miles.',
  valid_trip           COMMENT 'True when fare, distance, and duration are positive.'
)
COMMENT 'Curated Genie-facing view for NYC taxi trip analytics. Use this view for fares, distance, duration, pickup/dropoff ZIPs, routes, and pickup-time trends.'
AS
SELECT
  tpep_pickup_datetime                                  AS pickup_ts,
  tpep_dropoff_datetime                                 AS dropoff_ts,
  CAST(tpep_pickup_datetime AS DATE)                    AS pickup_date,
  DATE_TRUNC('MONTH', tpep_pickup_datetime)             AS pickup_month,
  HOUR(tpep_pickup_datetime)                            AS pickup_hour,
  CASE DAYOFWEEK(tpep_pickup_datetime)
    WHEN 1 THEN 'Sunday'  WHEN 2 THEN 'Monday'   WHEN 3 THEN 'Tuesday'
    WHEN 4 THEN 'Wednesday' WHEN 5 THEN 'Thursday' WHEN 6 THEN 'Friday'
    WHEN 7 THEN 'Saturday'
  END                                                   AS pickup_day_of_week,
  DAYOFWEEK(tpep_pickup_datetime)                       AS pickup_day_number,
  CASE
    WHEN HOUR(tpep_pickup_datetime) BETWEEN  6 AND 11 THEN 'Morning'
    WHEN HOUR(tpep_pickup_datetime) BETWEEN 12 AND 16 THEN 'Afternoon'
    WHEN HOUR(tpep_pickup_datetime) BETWEEN 17 AND 21 THEN 'Evening'
    ELSE 'Night'
  END                                                   AS time_of_day,
  trip_distance                                         AS trip_distance_miles,
  fare_amount                                           AS fare_amount_usd,
  CAST(pickup_zip  AS STRING)                           AS pickup_zip,
  CAST(dropoff_zip AS STRING)                           AS dropoff_zip,
  CONCAT(CAST(pickup_zip AS STRING), '-', CAST(dropoff_zip AS STRING)) AS route,
  TIMESTAMPDIFF(MINUTE, tpep_pickup_datetime, tpep_dropoff_datetime)   AS duration_minutes,
  CASE WHEN trip_distance > 0 THEN fare_amount / trip_distance END     AS fare_per_mile,
  trip_distance > 0
    AND fare_amount > 0
    AND TIMESTAMPDIFF(MINUTE, tpep_pickup_datetime, tpep_dropoff_datetime) > 0
                                                        AS valid_trip
FROM demo.nyctaxi.trips_raw
WHERE tpep_pickup_datetime IS NOT NULL
  AND tpep_dropoff_datetime IS NOT NULL;
```

### 3.5 Phase 4 — Profile validation

One round-trip; record the output in your worksheet so the §3.7.3 text instructions are anchored in reality:

```sql
SELECT
  COUNT(*)                                                                  AS rows_total,
  COUNT_IF(valid_trip)                                                      AS rows_valid,
  MIN(pickup_date)                                                          AS first_pickup_date,
  MAX(pickup_date)                                                          AS last_pickup_date,
  ROUND(AVG(CASE WHEN valid_trip THEN fare_amount_usd END), 2)              AS avg_valid_fare_usd,
  ROUND(AVG(CASE WHEN valid_trip THEN trip_distance_miles END), 2)          AS avg_valid_distance_miles,
  COUNT_IF(trip_distance_miles <= 0)                                        AS non_positive_distance_rows,
  COUNT_IF(fare_amount_usd <= 0)                                            AS non_positive_fare_rows,
  COUNT_IF(duration_minutes <= 0)                                           AS non_positive_duration_rows
FROM demo.nyctaxi.v_trips_genie;
```

Expected for the public `samples.nyctaxi.trips` snapshot: `rows_total = 21,932`, `rows_valid = 21,770`, range `2016-01-01 .. 2016-02-29`, `avg_valid_fare_usd ≈ 12.32`, `avg_valid_distance_miles ≈ 2.87`. If your numbers differ wildly, the upstream sample changed — update your benchmarks.

### 3.6 Phase 5 — Create the Genie Space (basics)

Via Databricks MCP / Claude Code, one call:

```text
create_or_update_genie(
  display_name      = "NYC Taxi Trips Genie (${monogram})",
  table_identifiers = ["demo.nyctaxi_${monogram}.v_trips_genie"],
  warehouse_id      = "<sql_warehouse_id>",
  description       = "Ask questions about NYC taxi trip counts, fares, trip distances, trip durations, pickup ZIPs, dropoff ZIPs, routes, and pickup-time trends.\n\nThis space uses the curated view demo.nyctaxi_${monogram}.v_trips_genie. Fare means metered fare_amount_usd only; it does not include tips, tolls, taxes, surcharges, or total amount. Location analysis is ZIP-code based. Dataset covers Jan 1 – Feb 29, 2016 (21,932 trips, 21,770 valid).",
  sample_questions  = [
    "What are the top 10 pickup ZIP codes by valid trip count?",
    "How do trips and average fare vary by hour of day?",
    "Which pickup-dropoff routes have the highest average fare with at least 20 trips?",
    "What is the average fare on weekdays versus weekends?",
    "Show fare per mile by time of day.",
    "What are the top pickup ZIPs in the latest month in the dataset?",
    "Which ZIP codes have the longest average trip distance?",
    "What is the average duration by day of week?"
  ]
)
```

UI fallback: **Workspace → Genie → New Space**, attach `demo.nyctaxi_${monogram}.v_trips_genie`, pick the Pro/Serverless warehouse, paste the description and the eight sample questions, and set the display name to `NYC Taxi Trips Genie (${monogram})`.

The call returns a `space_id` (UUID-ish hex string). **Record it in §1.1** — it's needed by the DAB binding in §4 and by any future Streamlit chat page.

### 3.7 Phase 6 — Deeper Genie configuration (UI today)

This is the part the MCP `create_or_update_genie` tool does **not** cover (today). Without it, the space technically works but answers drift and the assistant misinterprets common asks (e.g. "last month" returning zero rows on the 2016-dated sample). Add the seven blocks below in **Configure → …** of the space.

#### 3.7.1 Synonyms (Configure → Data → `v_trips_genie` → column → Synonyms)

| Column | Synonyms |
|---|---|
| `fare_amount_usd` | fare, cost, price, metered fare, fare amount |
| `trip_distance_miles` | distance, miles, trip length |
| `duration_minutes` | duration, trip time, ride time, minutes |
| `pickup_zip` | pickup, origin, start ZIP, pickup location |
| `dropoff_zip` | dropoff, destination, end ZIP, drop-off location |
| `route` | route, OD pair, origin-destination, pickup-dropoff |
| `pickup_ts` | pickup time, trip time, ride time |
| `pickup_date` | date, trip date, ride date |
| `pickup_month` | month, trip month, monthly |
| `pickup_hour` | hour, hour of day, time of day |
| `pickup_day_of_week` | day, weekday, day of week |
| `time_of_day` | morning, afternoon, evening, night, daypart |
| `valid_trip` | clean trip, valid ride, valid record |

#### 3.7.2 Prompt / entity matching

Enable for these string / categorical columns (helps Genie pick the right column when a user types a ZIP, a route, or "Saturday"):

```
pickup_zip
dropoff_zip
route
pickup_day_of_week
time_of_day
```

Leave it off for numeric measures (`fare`, `distance`, `duration`, `hour`).

#### 3.7.3 Text instructions (Configure → Instructions → Text)

```text
Purpose:
Answer questions about NYC taxi trips using demo.nyctaxi.v_trips_genie.

Default table:
Always use demo.nyctaxi.v_trips_genie unless the user explicitly asks for another accessible table.

Metric definitions:
- "Trips" means COUNT(*) unless the user asks for valid trips.
- For fare, distance, duration, route, and fare-per-mile analysis, filter to valid_trip = true unless the user explicitly asks otherwise.
- "Fare", "cost", "price", and "revenue" mean fare_amount_usd only.
- fare_amount_usd excludes tips, tolls, taxes, surcharges, and total trip amount.
- "Distance" is trip_distance_miles.
- "Duration" is duration_minutes.
- "Route" means pickup_zip to dropoff_zip.
- For time-based questions, use pickup_ts, pickup_date, pickup_month, pickup_hour, or pickup_day_of_week based on the requested grain.
- Use pickup time as the default trip time unless the user explicitly asks about dropoff time.

Date rules:
- First inspect or respect the date range in the data.
- Do not use CURRENT_DATE for sample-data questions unless the user explicitly asks for a current-date-relative calculation.
- If the user says "latest month", use the maximum pickup_month in the dataset.
- If the user says "last month" and does not specify whether they mean calendar last month or latest month in the dataset, ask a clarification question.

Ambiguity rules:
- If the user asks for "top", "best", "biggest", or "most important" without a metric, ask whether to rank by trip count, total fare, average fare, average distance, duration, or fare per mile.
- If the user asks about "area" or "location" without specifying pickup or dropoff, ask whether they mean pickup_zip, dropoff_zip, or route.
- If the user asks about boroughs, neighborhoods, airports, taxi zones, payment type, tips, tolls, passenger count, or total amount, explain that this space does not contain those fields unless an additional dimension/table is added.

Formatting:
- Round monetary values, distances, durations, and fare-per-mile metrics to two decimals.
- Include the date range used in time-based summaries.
- In summaries, mention the main columns used.
```

#### 3.7.4 SQL expressions (Configure → Instructions → SQL Expressions)

| Type | Name | Code | Synonyms |
|---|---|---|---|
| Filter | Valid trips | `valid_trip = true` | clean trips, valid rides, good trips |
| Measure | Trip count | `COUNT(*)` | trips, rides, number of trips |
| Measure | Valid trip count | `COUNT_IF(valid_trip)` | valid trips, clean trips |
| Measure | Total fare | `SUM(CASE WHEN valid_trip THEN fare_amount_usd END)` | revenue, total revenue, total fare |
| Measure | Average fare | `AVG(CASE WHEN valid_trip THEN fare_amount_usd END)` | avg fare, average price |
| Measure | Average distance | `AVG(CASE WHEN valid_trip THEN trip_distance_miles END)` | avg distance, average miles |
| Measure | Average duration | `AVG(CASE WHEN valid_trip THEN duration_minutes END)` | avg duration, average trip time |
| Measure | Aggregate fare per mile | `SUM(CASE WHEN valid_trip THEN fare_amount_usd END) / NULLIF(SUM(CASE WHEN valid_trip THEN trip_distance_miles END), 0)` | revenue per mile, total fare per mile |
| Measure | Average trip fare per mile | `AVG(CASE WHEN valid_trip THEN fare_per_mile END)` | avg fare per mile, average trip price per mile |
| Dimension | Pickup month | `pickup_month` | month, monthly |
| Dimension | Pickup hour | `pickup_hour` | hour, hour of day |
| Dimension | Pickup day of week | `pickup_day_of_week` | day, weekday |
| Dimension | Time of day | `time_of_day` | morning, afternoon, evening, night |
| Dimension | Route | `route` | OD pair, pickup-dropoff |

Define both *aggregate* and *average-of-per-trip* fare-per-mile under separate names — they compute different things and Genie will pick the closest match by synonym.

#### 3.7.5 Example SQL queries (Configure → Instructions → Example SQL)

Six examples; each one is a (prompt → SQL) pair. Paste each as a single example in the UI.

**1. Top pickup ZIPs**

Prompt: `What are the top 10 pickup ZIP codes by number of valid trips?`

```sql
SELECT pickup_zip,
       COUNT(*)                              AS trips,
       ROUND(AVG(fare_amount_usd), 2)        AS avg_fare_usd,
       ROUND(AVG(trip_distance_miles), 2)    AS avg_distance_miles
FROM   demo.nyctaxi.v_trips_genie
WHERE  valid_trip = true
GROUP  BY pickup_zip
ORDER  BY trips DESC
LIMIT  10;
```

**2. Trips and fare by hour**

Prompt: `How do trips and average fare vary by hour of day?`

```sql
SELECT pickup_hour,
       COUNT(*)                              AS trips,
       ROUND(AVG(fare_amount_usd), 2)        AS avg_fare_usd,
       ROUND(AVG(trip_distance_miles), 2)    AS avg_distance_miles
FROM   demo.nyctaxi.v_trips_genie
WHERE  valid_trip = true
GROUP  BY pickup_hour
ORDER  BY pickup_hour;
```

**3. Latest month in the dataset**

Prompt: `Top 10 pickup ZIPs in the latest month in the dataset`

```sql
WITH latest AS (
  SELECT DATE_TRUNC('MONTH', MAX(pickup_date)) AS latest_month
  FROM   demo.nyctaxi.v_trips_genie
)
SELECT pickup_zip,
       COUNT(*)                          AS trips,
       ROUND(SUM(fare_amount_usd), 2)    AS total_fare_usd,
       ROUND(AVG(fare_amount_usd), 2)    AS avg_fare_usd
FROM   demo.nyctaxi.v_trips_genie, latest
WHERE  valid_trip = true
  AND  pickup_date >= latest.latest_month
  AND  pickup_date <  ADD_MONTHS(latest.latest_month, 1)
GROUP  BY pickup_zip
ORDER  BY trips DESC
LIMIT  10;
```

**4. Routes with highest average fare**

Prompt: `Which routes have the highest average fare, excluding rare routes?`

```sql
SELECT route, pickup_zip, dropoff_zip,
       COUNT(*)                              AS trips,
       ROUND(AVG(fare_amount_usd), 2)        AS avg_fare_usd,
       ROUND(AVG(trip_distance_miles), 2)    AS avg_distance_miles,
       ROUND(AVG(duration_minutes), 2)       AS avg_duration_minutes
FROM   demo.nyctaxi.v_trips_genie
WHERE  valid_trip = true
GROUP  BY route, pickup_zip, dropoff_zip
HAVING COUNT(*) >= 20
ORDER  BY avg_fare_usd DESC
LIMIT  10;
```

**5. Weekday vs weekend**

Prompt: `What is the average fare on weekdays versus weekends?`

```sql
SELECT CASE WHEN pickup_day_number IN (1, 7) THEN 'Weekend' ELSE 'Weekday' END
                                             AS weekday_weekend,
       COUNT(*)                              AS trips,
       ROUND(AVG(fare_amount_usd), 2)        AS avg_fare_usd,
       ROUND(AVG(trip_distance_miles), 2)    AS avg_distance_miles,
       ROUND(AVG(duration_minutes), 2)       AS avg_duration_minutes
FROM   demo.nyctaxi.v_trips_genie
WHERE  valid_trip = true
GROUP  BY CASE WHEN pickup_day_number IN (1, 7) THEN 'Weekend' ELSE 'Weekday' END
ORDER  BY weekday_weekend;
```

**6. Fare per mile by time of day**

Prompt: `Show fare per mile by time of day.`

```sql
SELECT time_of_day,
       COUNT(*)                                                            AS trips,
       ROUND(SUM(fare_amount_usd) / NULLIF(SUM(trip_distance_miles), 0), 2) AS aggregate_fare_per_mile,
       ROUND(AVG(fare_per_mile), 2)                                         AS avg_trip_fare_per_mile
FROM   demo.nyctaxi.v_trips_genie
WHERE  valid_trip = true
GROUP  BY time_of_day
ORDER  BY CASE time_of_day
            WHEN 'Morning'   THEN 1
            WHEN 'Afternoon' THEN 2
            WHEN 'Evening'   THEN 3
            WHEN 'Night'     THEN 4
          END;
```

#### 3.7.6 Trusted parameterised examples

In the Example SQL editor, mark the prompt as "trusted" and declare parameters. Genie labels the resulting answer as *Trusted* when it matches.

**Pickup ZIP profile** (`pickup_zip` parameter, String)

Prompt: `Show trip metrics for pickup ZIP 10019`

```sql
SELECT pickup_zip,
       COUNT(*)                              AS trips,
       ROUND(SUM(fare_amount_usd), 2)        AS total_fare_usd,
       ROUND(AVG(fare_amount_usd), 2)        AS avg_fare_usd,
       ROUND(AVG(trip_distance_miles), 2)    AS avg_distance_miles,
       ROUND(AVG(duration_minutes), 2)       AS avg_duration_minutes
FROM   demo.nyctaxi.v_trips_genie
WHERE  valid_trip = true
  AND  pickup_zip = :pickup_zip
GROUP  BY pickup_zip;
```

**Date-range trend** (`start_date`, `end_date` parameters, Date)

Prompt: `Show daily trips and average fare between two dates`

```sql
SELECT pickup_date,
       COUNT(*)                              AS trips,
       ROUND(SUM(fare_amount_usd), 2)        AS total_fare_usd,
       ROUND(AVG(fare_amount_usd), 2)        AS avg_fare_usd
FROM   demo.nyctaxi.v_trips_genie
WHERE  valid_trip = true
  AND  pickup_date >= :start_date
  AND  pickup_date <  :end_date
GROUP  BY pickup_date
ORDER  BY pickup_date;
```

#### 3.7.7 Common questions (Configure → Common questions)

```text
What are the top 10 pickup ZIP codes by valid trip count?
How do trips and average fare vary by hour of day?
Which pickup-dropoff routes have the highest average fare?
What is the average fare on weekdays versus weekends?
Show fare per mile by time of day.
What are the top pickup ZIPs in the latest month in the dataset?
Which ZIP codes have the longest average trip distance?
```

#### 3.7.8 Benchmarks (Configure → Benchmarks)

For each question below, add it as a benchmark and paste the gold SQL from §3.7.5 / §3.7.6. Also add 2–4 alternate phrasings ("busiest pickup ZIPs", "which origins have the most rides", …) under the same benchmark so Genie is tested against realistic variation.

```text
What are the top 10 pickup ZIP codes by number of valid trips?
Which pickup ZIPs have the highest average fare?
How do trips vary by pickup hour?
What is the average fare on weekdays versus weekends?
Which routes have the highest average fare with at least 20 trips?
Show fare per mile by time of day.
What is the latest month in the dataset?
Top pickup ZIPs in the latest month in the dataset.
Which pickup ZIP has the longest average trip distance?
What is the average duration by day of week?
```

### 3.8 Claude Code prompt — run §3.2 → §3.6 + walkthrough for §3.7

Phases 1–5 are fully scriptable through the Databricks MCP. Phase 6 (synonyms, instructions, SQL expressions, etc.) needs UI clicks today. Paste this prompt; Claude will do the scriptable work and then print a structured checklist for the UI work.

```text
Set up the NYC taxi Genie Space described in docs/plans/0_D_genie_setup.md.

Inputs from §1.1:
- catalog_name:        demo                   (shared — do NOT create)
- schema_name:         nyctaxi_${monogram}    (per-operator — you create this)
- raw_table:           trips_raw
- curated_view:        v_trips_genie
- source_table:        samples.nyctaxi.trips
- sql_warehouse_id:    <fill from §1.1>
- genie_space_name:    NYC Taxi Trips Genie (${monogram})

Do the following idempotently and report each change you make:

1. Phase 1 — DO NOT create the `demo` catalog (shared infrastructure). Only
   manage_uc_objects create schema `demo.nyctaxi_${monogram}`. Skip if it
   already exists. If `demo` itself is missing, STOP and ask the user to
   request the metastore admin to provision it.
2. Phase 2 — execute_sql for the DEEP CLONE, ANALYZE, table comment,
   and the six ALTER COLUMN comments from §3.3. Use the
   `CREATE TABLE IF NOT EXISTS ... DEEP CLONE` form (the OR REPLACE form
   trips the MCP tool).
3. Phase 3 — execute_sql for the curated view in §3.4.
4. Phase 4 — execute_sql for the profile query in §3.5; print the result.
   STOP if rows_total is 0 or last_pickup_date is missing.
5. Phase 5 — create_or_update_genie with the display name, description,
   the eight sample questions, the warehouse_id, and the single attached
   table `demo.nyctaxi_${monogram}.v_trips_genie`. Print the returned
   `space_id` and tell me to record it in §1.1.

6. Phase 6 — DO NOT try to script this. Instead, print a one-screen
   checklist that lists, in order:
   - the synonyms table (§3.7.1) by column,
   - the prompt-matching column list (§3.7.2),
   - the text instructions block (§3.7.3),
   - the 14 SQL expressions (§3.7.4),
   - the six example SQL prompts (§3.7.5) — titles only,
   - the two trusted parameterised examples (§3.7.6) — titles only,
   - the common-questions list (§3.7.7),
   - the benchmark questions (§3.7.8).
   For each item, put a copy-pasteable hint pointing me to the
   exact Genie UI location (`Configure → Data → <col> → Synonyms`, etc.).

Before mutating anything, print the plan of changes and wait for me to
confirm. Do not touch any object outside `demo.nyctaxi_${monogram}.*` or
the Genie Space named above. Never touch the `demo` catalog itself — it is shared.
```

---

## 4. DAB updates

The Genie Space is **not** created by DAB — DAB owns the App + permissions + resource bindings only. Once the space exists (§3.6), bind it to the App so the Streamlit runtime resolves `valueFrom: genie-space` to the actual space ID. This is what a future chat-page plan will assume.

### 4.1 New variable

Append to `databricks.yml`:

```yaml
variables:
  # ... existing variables ...
  genie_space_id:
    description: "ID of the NYC Taxi Trips Genie space (captured after create_or_update_genie)."
```

### 4.2 App resource binding

Append under `resources.apps.streamlit-demo.resources`:

```yaml
resources:
  apps:
    streamlit-demo:
      # ... existing config ...
      resources:
        # ... existing entries (e.g. sql-warehouse if you have the Sample Data page) ...
        - name: genie-space
          genie_space:
            name: NYC Taxi Trips Genie
            space_id: ${var.genie_space_id}
            permission: CAN_RUN
```

Permission options on the binding: `CAN_VIEW`, `CAN_RUN`, `CAN_EDIT`, `CAN_MANAGE`. `CAN_RUN` is the minimum for the app SP to start conversations and execute Genie's generated SQL via the Conversation API.

### 4.3 Target value

```yaml
targets:
  dev:
    variables:
      # ... existing ...
      genie_space_id: "<paste the space_id captured in §1.1>"
```

### 4.4 App env wiring (forward-looking — actual env var added when the page is built)

When a chat page is implemented later, `app.yaml` will gain:

```yaml
env:
  # ... existing entries ...
  - name: GENIE_SPACE_ID
    valueFrom: genie-space
```

This is **not** added now — `get_env("GENIE_SPACE_ID")` only matters once a page calls it. Mentioning it here so the binding key (`genie-space`) is consistent across the bundle and `app.yaml`.

### 4.5 Redeploy

```bash
databricks bundle validate -t dev
databricks bundle deploy  -t dev
```

The bundle adds the Genie resource to the App's resource list. Nothing in the App's source needs to change yet.

---

## 5. Verification & next steps

### 5.1 Object verification (run as the deploy SP or as your user)

```sql
-- shared catalog present (you do not own it; just confirm it's there)
SHOW CATALOGS LIKE 'demo';
-- your per-operator schema present
SHOW SCHEMAS IN demo LIKE 'nyctaxi_${monogram}';

-- table cloned, comments applied
DESCRIBE EXTENDED demo.nyctaxi_${monogram}.trips_raw;

-- view present with all 16 columns
DESCRIBE EXTENDED demo.nyctaxi_${monogram}.v_trips_genie;

-- profile sanity (see §3.5 for expected numbers)
SELECT COUNT(*) AS rows_total, COUNT_IF(valid_trip) AS rows_valid,
       MIN(pickup_date) AS first_pickup_date, MAX(pickup_date) AS last_pickup_date
FROM   demo.nyctaxi_${monogram}.v_trips_genie;
```

### 5.2 Genie sanity (UI)

Open **Workspace → Genie → NYC Taxi Trips Genie**, then ask each of these and confirm Genie's generated SQL filters on `valid_trip` and uses the curated view (not the raw table):

- *"What are the top 10 pickup ZIP codes by valid trip count?"*
- *"Average fare on weekdays versus weekends?"*
- *"Show fare per mile by time of day."*

After §3.7 is applied, each of these should generate SQL within one or two seconds, return ≤10 rows, and round monetary values to 2 decimals. If Genie picks `trips_raw` instead of `v_trips_genie`, the §3.7.3 "Default table" instruction is missing or misspelled.

### 5.3 Sharing (one-time)

Grant `<user_group_app>` from `0_A_initial_setup.md`. The shared `demo` catalog typically already exposes `USE CATALOG` to the operator group, but downstream end-users typically aren't members of that group — so re-grant `USE CATALOG` to your app's audience group here:

```sql
-- Grant on the SHARED catalog (idempotent; safe to re-run):
GRANT USE CATALOG ON CATALOG demo                                       TO `<user_group_app>`;
-- Grant on YOUR per-operator schema + view:
GRANT USE SCHEMA  ON SCHEMA  demo.nyctaxi_${monogram}                   TO `<user_group_app>`;
GRANT SELECT      ON TABLE   demo.nyctaxi_${monogram}.v_trips_genie     TO `<user_group_app>`;
```

Plus, in the Genie Space UI: **Share → add `<user_group_app>` with CAN_RUN**.

Also confirm the same group has `CAN_USE` on the SQL warehouse — without it, Genie's query execution returns a permission error to the end user even though they can open the space.

### 5.4 Bundle verification

```bash
databricks bundle validate -t dev
databricks bundle summary  -t dev   # shows the genie-space binding under apps.streamlit-demo.resources
```

### 5.5 Iteration loop

After sharing the space, watch **Monitor** weekly:

1. Triage thumbs-down / "Fix it" / "Request review" entries.
2. For wrong answers, click **Show code** — confirm `valid_trip` filter and the curated view.
3. Update the right block in §3.7 (synonyms / SQL expression / example SQL / instruction) and re-run benchmarks.
4. If the same wrong-shape answer appears two weeks running, add a benchmark for it so regressions are caught the next time §3.7 is touched.

### 5.6 What's next

- **Streamlit chat page.** A per-page plan (e.g. `2_genie_chat_page.md`) lays this on top: imports `init_page`, reads `GENIE_SPACE_ID` via `get_env`, uses `workspace_client_app()` for `w.genie.start_conversation_and_wait(...)`, and renders attachments with `st.chat_message`. The DAB binding in §4 and the `genie-space` key keep the page brand-agnostic.
- **More data dimensions.** If users want boroughs / payment type / tips / `total_amount`, those columns don't exist in `samples.nyctaxi.trips`. Either bring in a richer source or rewrite the §3.7.3 ambiguity rule to call out the missing dimensions earlier in the chat.

---

## What to avoid

- **Attaching `samples.nyctaxi.trips` directly to Genie.** Read-only, no comments, no statistics — Genie answer quality drops materially. Always go through the curated view.
- **Attaching both `trips_raw` and `v_trips_genie`.** Genie has two ways to answer the same question, so synonyms and instructions stop being authoritative. One curated object only.
- **`CREATE OR REPLACE TABLE … DEEP CLONE` through the MCP `execute_sql` tool.** Currently errors with an unrelated Python message; use `CREATE TABLE IF NOT EXISTS … DEEP CLONE` when scripting through MCP.
- **`CURRENT_DATE`-relative filters in benchmark questions** for this dataset. The data ends Feb 29 2016. Phrase it as "latest month in the dataset" instead.
- **Using a Classic SQL warehouse.** Genie requires Pro or Serverless.
- **`AVG(fare_amount / distance)` and `SUM(fare) / SUM(distance)` as the same metric.** They're different (per-trip mean vs aggregate); define both under distinct names so Genie matches the user's intent by synonym.
- **Treating "not attached to the space" as a hard data boundary.** A user with UC `SELECT` on another table can ask Genie about it through the curated view's joins or by editing the generated SQL. Real isolation must come from UC grants and row filters, not from the Genie space attachment set.
