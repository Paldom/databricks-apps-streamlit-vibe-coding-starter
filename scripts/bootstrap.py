"""Bootstrap the Streamlit-demo data layer (DAB can't own these objects).

What this script creates / refreshes (idempotent):

  1. demo.nyctaxi.trips_raw          — DEEP CLONE of samples.nyctaxi.trips
                                        (no DAB `tables:` resource type)
  2. ANALYZE TABLE … COMPUTE STATISTICS FOR ALL COLUMNS
  3. Table + column comments on trips_raw
  4. demo.nyctaxi.v_trips_genie      — curated business-facing view
                                        (no DAB `views:` resource type)
  5. demo.nyctaxi.trips_for_sync     — materialised table with synthetic
                                        trip_id PK, used as the Lakebase
                                        sync source
                                        (no DAB `tables:` resource type)
  6. GRANT SELECT ON VIEW demo.nyctaxi.v_trips_genie TO <app_sp>
                                        (view-level grants can't go under
                                        the bundle's `schemas:` grants
                                        block because DAB doesn't own the
                                        view)
  7. Upload resources/*.pdf to /Volumes/demo/knowledge_assistant/docs
                                        (no DAB volume-file resource)

What DAB owns instead (do NOT run this for those — `bundle deploy` does):
  * Schema demo.nyctaxi, schema demo.knowledge_assistant
  * Volume demo.knowledge_assistant.docs
  * Lakebase instance + UC catalog + synced table
  * The AI/BI dashboard
  * The app + its resource bindings

What is OUT-of-scope for this script (run those manually, once per workspace):
  * Create `demo` catalog                          (Workspace → Catalog UI)
  * Create the Genie Space                         (docs/plans/0_D §3.6)
  * Create the Knowledge Assistant + sources       (docs/plans/6_*.md §3)
  * Create the Multi-Agent Supervisor              (docs/plans/7_*.md §3)
  * Postgres-side GRANTs on the Lakebase synced
    table (after the App first connects)           (docs/plans/2_*.md §3.4)

Usage:
    # one-off
    uv run python scripts/bootstrap.py \
        --warehouse-id 1463663e9d511f7c \
        --app-sp-client-id 96ac8af2-aac9-42a6-8e54-eec78b859126 \
        --pdf-source resources/

    # or set DATABRICKS_WAREHOUSE_ID + DATABRICKS_APP_SP_CLIENT_ID env vars
    # and run without flags.

Requires the Databricks CLI to be authenticated (`databricks auth login`).
The script uses the unified SDK auth chain — workspace profiles, OAuth user
tokens, and M2M secrets all work.
"""
from __future__ import annotations

import argparse
import logging
import os
import pathlib
import sys

from databricks import sql
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("bootstrap")


# Order matters: each statement is idempotent and depends only on earlier ones.
# Statements are run sequentially through a single SQL warehouse session.
SQL_STATEMENTS: list[tuple[str, str]] = [
    (
        "1. trips_raw — deep clone of samples.nyctaxi.trips",
        # CREATE OR REPLACE TABLE … DEEP CLONE trips the MCP execute_sql path;
        # CREATE TABLE IF NOT EXISTS … DEEP CLONE works in both MCP and CLI.
        "CREATE TABLE IF NOT EXISTS demo.nyctaxi.trips_raw "
        "DEEP CLONE samples.nyctaxi.trips",
    ),
    (
        "2. ANALYZE STATISTICS",
        "ANALYZE TABLE demo.nyctaxi.trips_raw COMPUTE STATISTICS FOR ALL COLUMNS",
    ),
    (
        "3a. COMMENT ON TABLE trips_raw",
        "COMMENT ON TABLE demo.nyctaxi.trips_raw IS "
        "'NYC taxi trip records cloned from samples.nyctaxi.trips. "
        "One row represents one taxi trip.'",
    ),
    (
        "3b. column comment — tpep_pickup_datetime",
        "ALTER TABLE demo.nyctaxi.trips_raw ALTER COLUMN tpep_pickup_datetime "
        "COMMENT 'Trip pickup timestamp. Use this as the default time dimension for trip analysis.'",
    ),
    (
        "3c. column comment — tpep_dropoff_datetime",
        "ALTER TABLE demo.nyctaxi.trips_raw ALTER COLUMN tpep_dropoff_datetime "
        "COMMENT 'Trip dropoff timestamp. Use only when users ask about dropoff time or trip duration.'",
    ),
    (
        "3d. column comment — trip_distance",
        "ALTER TABLE demo.nyctaxi.trips_raw ALTER COLUMN trip_distance "
        "COMMENT 'Trip distance in miles.'",
    ),
    (
        "3e. column comment — fare_amount",
        "ALTER TABLE demo.nyctaxi.trips_raw ALTER COLUMN fare_amount "
        "COMMENT 'Metered fare amount in USD. Excludes tips, tolls, taxes, and surcharges.'",
    ),
    (
        "3f. column comment — pickup_zip",
        "ALTER TABLE demo.nyctaxi.trips_raw ALTER COLUMN pickup_zip "
        "COMMENT 'ZIP code where the taxi trip started.'",
    ),
    (
        "3g. column comment — dropoff_zip",
        "ALTER TABLE demo.nyctaxi.trips_raw ALTER COLUMN dropoff_zip "
        "COMMENT 'ZIP code where the taxi trip ended.'",
    ),
    (
        "4. v_trips_genie — curated business view",
        """CREATE OR REPLACE VIEW demo.nyctaxi.v_trips_genie
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
  AND tpep_dropoff_datetime IS NOT NULL""",
    ),
    (
        "5a. trips_for_sync — materialised, used as the Lakebase sync source",
        """CREATE OR REPLACE TABLE demo.nyctaxi.trips_for_sync
COMMENT 'Materialised copy of demo.nyctaxi.v_trips_genie with a synthetic primary key, used as the source for the Lakebase synced table demo.nyctaxi.trips_synced.'
AS
SELECT
  ROW_NUMBER() OVER (ORDER BY pickup_ts, pickup_zip, dropoff_zip) AS trip_id,
  pickup_ts, dropoff_ts,
  pickup_zip, dropoff_zip, route,
  trip_distance_miles, fare_amount_usd,
  duration_minutes, fare_per_mile,
  pickup_day_of_week, time_of_day, valid_trip
FROM demo.nyctaxi.v_trips_genie""",
    ),
    (
        "5b. trips_for_sync.trip_id NOT NULL (required for PK)",
        "ALTER TABLE demo.nyctaxi.trips_for_sync ALTER COLUMN trip_id SET NOT NULL",
    ),
    # The PK constraint must be wrapped to be idempotent — re-running the
    # script would otherwise fail with "constraint already exists". We
    # drop-then-add so the script stays restartable.
    (
        "5c. trips_for_sync — drop any existing PK constraint",
        "ALTER TABLE demo.nyctaxi.trips_for_sync DROP CONSTRAINT IF EXISTS trips_for_sync_pk",
    ),
    (
        "5d. trips_for_sync — add PRIMARY KEY (trip_id) constraint",
        "ALTER TABLE demo.nyctaxi.trips_for_sync ADD CONSTRAINT trips_for_sync_pk PRIMARY KEY (trip_id)",
    ),
]


def _grant_view_select(cur, app_sp: str) -> None:
    """Grant SELECT on the curated view to the App SP.

    The schema-level grants in `databricks.yml` cover `SELECT` on every
    table/view inside `demo.nyctaxi` already — this is redundant but
    documented as a defensive belt-and-braces step (and makes the script
    self-sufficient in workspaces that override schema grants).
    """
    cur.execute(
        f'GRANT SELECT ON VIEW demo.nyctaxi.v_trips_genie TO `{app_sp}`'
    )


def run_sql(warehouse_id: str, app_sp_client_id: str | None) -> None:
    """Execute the SQL_STATEMENTS sequentially through the configured warehouse."""
    cfg = Config()
    if not cfg.host:
        sys.exit("ERROR: workspace host not set. Run `databricks auth login` first.")

    log.info("Connecting to SQL warehouse %s @ %s", warehouse_id, cfg.host)
    server_hostname = cfg.host.replace("https://", "").rstrip("/")

    with sql.connect(
        server_hostname=server_hostname,
        http_path=f"/sql/1.0/warehouses/{warehouse_id}",
        credentials_provider=lambda: cfg.authenticate,
    ) as conn, conn.cursor() as cur:
        for label, stmt in SQL_STATEMENTS:
            log.info("→ %s", label)
            cur.execute(stmt)

        if app_sp_client_id:
            log.info("→ 6. GRANT SELECT on v_trips_genie to app SP %s", app_sp_client_id)
            _grant_view_select(cur, app_sp_client_id)

    log.info("SQL bootstrap complete.")


def upload_pdfs(volume_path: str, source_dir: pathlib.Path) -> None:
    """Upload every *.pdf under `source_dir` to the UC volume."""
    pdfs = sorted(source_dir.glob("*.pdf"))
    if not pdfs:
        log.warning("No PDFs found under %s — skipping upload.", source_dir)
        return

    log.info("Uploading %d PDFs from %s → %s", len(pdfs), source_dir, volume_path)
    w = WorkspaceClient()
    for pdf in pdfs:
        remote = f"{volume_path.rstrip('/')}/{pdf.name}"
        log.info("  → %s", remote)
        with pdf.open("rb") as fh:
            w.files.upload(file_path=remote, contents=fh, overwrite=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--warehouse-id",
        default=os.environ.get("DATABRICKS_WAREHOUSE_ID"),
        help="SQL Warehouse ID for DDL execution. Required.",
    )
    parser.add_argument(
        "--app-sp-client-id",
        default=os.environ.get("DATABRICKS_APP_SP_CLIENT_ID"),
        help="App service-principal client ID — granted SELECT on the curated view.",
    )
    parser.add_argument(
        "--volume-path",
        default="/Volumes/demo/knowledge_assistant/docs",
        help="UC volume path to upload PDFs into.",
    )
    parser.add_argument(
        "--pdf-source",
        default="resources",
        help="Local folder containing source *.pdf files.",
    )
    parser.add_argument(
        "--skip-sql", action="store_true",
        help="Skip the SQL bootstrap (tables / views / grants).",
    )
    parser.add_argument(
        "--skip-uploads", action="store_true",
        help="Skip uploading PDFs to the UC volume.",
    )
    args = parser.parse_args()

    if not args.skip_sql:
        if not args.warehouse_id:
            sys.exit(
                "ERROR: --warehouse-id (or DATABRICKS_WAREHOUSE_ID) is required "
                "unless --skip-sql is set."
            )
        run_sql(args.warehouse_id, args.app_sp_client_id)

    if not args.skip_uploads:
        upload_pdfs(args.volume_path, pathlib.Path(args.pdf_source))


if __name__ == "__main__":
    main()
