"""Lakebase Sync — query the synced NYC taxi trips table over Postgres.

Reads from the Lakebase-side replica of ``demo.nyctaxi.trips_for_sync`` which
was synced from Unity Catalog via the ``synced_database_tables`` DAB resource
(see databricks.yml). Connects with the app service principal: a fresh OAuth
token is minted on every Postgres ``connect()`` so long-lived pools never see
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
