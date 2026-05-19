# Project Summary — Databricks Apps Streamlit Starter

A narrative summary that works as documentation and as a slide-deck source. Each `## Chapter N · …` is one logical unit — copy a chapter into a slide, or read top-to-bottom as a primer.

Audience: a mix of executive (decision-makers) and technical (implementers). The chapters lead with **why each step matters** and **how to do it on Databricks**, not the specific UUIDs / endpoint names this build happens to have produced.

---

## Chapter 1 · Executive Summary

This project is a **production-shaped starter** for building Streamlit applications on the Databricks Apps platform. It walks the full Databricks Data Intelligence stack — Unity Catalog, SQL Warehouses, AI/BI Dashboards, AI/BI Genie, Lakebase, Knowledge Assistant, and the Multi-Agent Supervisor — as seven feature-page implementation plans under `docs/plans/`, each replayable in a working day by a developer with Claude Code (or any LLM-driven dev environment). The repo itself ships only the scaffolding (utils, design system, bundle skeleton, CI/CD); the feature pages get built by following the plans.

The point isn't the specific dataset (we use the public NYC taxi sample + three fictional Northwind PDFs). The point is the **shape**: each capability is wired up the way Databricks intends — governance through Unity Catalog, serverless compute through SQL Warehouses, agent orchestration through Agent Bricks, deploys through Databricks Asset Bundles — so the same shape can carry your real data on day one.

Every step is also documented as a standalone implementation plan in `docs/plans/`. The plans are designed to be replayable by a developer with Claude Code (or any LLM-driven dev environment) against their own workspace — so re-creating the demo against a customer's data is a working day, not a sprint.

**Naming convention — monogram suffix.** Shared Databricks workspaces are common, so every resource this project creates is suffixed with the developer's monogram (2–3 lowercase initials derived from `databricks current-user me` → `displayName`, e.g. "Alex Mae Tan" → `amt`). UC objects use underscore form (`demo_amt.nyctaxi.v_trips_genie`); App / Lakebase / serving-endpoint names use hyphen form (`streamlit-demo-amt`); Genie / KA / supervisor display names append `(${monogram})` in parentheses. The convention is captured once in `0_A_initial_setup.md` §1.0 and every later plan inherits it.

**What you can show in a 15-minute demo (after running the plans):** open a UC table, watch it surface in a Postgres view, drop into an embedded BI dashboard, ask the same data conversational questions in Genie, query a separate set of governed PDFs in a chat that cites sources, then ask one supervisor agent a cross-domain question that fans out to both specialists — all without leaving the Streamlit app.

---

## Chapter 2 · Why Databricks Apps as the Host

**Databricks Apps** is Databricks' native hosting layer for data and AI applications. It exists because the alternatives — running Streamlit on a separate VM, exporting data to a hosted app platform, building an internal portal in a SaaS BI tool — each force you to **leave the governance plane**.

| What Apps gives you natively | Why it matters |
|---|---|
| Serverless compute, no infrastructure | Time-to-first-page is minutes, not weeks. No load balancers, no certificates, no patching. |
| OAuth and Unity Catalog integration | The app inherits Databricks SSO; Streamlit can call SQL warehouses, Genie, Agent Bricks endpoints with the user's identity (OBO) or the app's service principal. |
| First-class for Python frameworks | Streamlit, Dash, Gradio, Flask, FastAPI all work; deploy via `databricks bundle deploy` or the UI. |
| Auto-provisioned service principal per app | Every app gets a workspace identity to which you can grant least-privilege permissions on warehouses, endpoints, and UC objects. |
| Logs, status, deployment history in-workspace | Operational visibility lives next to the data, not in a separate observability stack. |

**Why we used it instead of standalone Streamlit Cloud:** the app needs `CAN_QUERY` on serving endpoints, `CAN_RUN` on a Genie space, `SELECT` on UC views, `CONNECT` on a Lakebase database. Hosting outside Databricks would require ferrying credentials and writing custom auth. Hosting on Apps means the SP is *already there* and grants are workspace-native.

**Implementation pattern**

1. **Define the app in `databricks.yml`** under `resources.apps.<name>`. The bundle declares the app's name, source path, and resource bindings (warehouses, Genie spaces, serving endpoints) — Databricks Apps creates the SP and injects connection env vars at runtime.
2. **Run command in `app.yaml`** (root): `command: ["streamlit", "run", "app.py"]`. The runtime sets `STREAMLIT_SERVER_PORT` / `STREAMLIT_SERVER_ADDRESS` automatically — never hardcode them.
3. **Deploy** via `databricks bundle deploy -t dev` followed by `databricks bundle run <app-name> -t dev`. `deploy` syncs source and updates resources; `run` (re)starts the app process. Both steps are required — `deploy` alone does *not* restart the app.

---

## Chapter 3 · The Governance Foundation — Unity Catalog

**Unity Catalog (UC)** is the spine of every chapter that follows. It's a unified governance layer for tables, views, functions, models, agents, dashboards, and unstructured files (volumes), exposed via a three-level namespace:

```
catalog.schema.object        e.g. demo.nyctaxi_${monogram}.v_trips_genie
```

**Why everything in this project goes through UC:** the same access-control model (`GRANT`/`REVOKE` per principal) covers structured tables, BI dashboards, Genie spaces, Knowledge Assistant endpoints, and Lakebase databases. There's no second permission system to learn, and no per-service IAM to configure — granting the app's service principal `CAN_QUERY` on a serving endpoint or `SELECT` on a view is the same shape of call.

**Why this matters for a public demo:** when we open the app on a workspace tour, the app is calling endpoints as its service principal. Every later customer will graduate to OBO (on-behalf-of the signed-in user), at which point UC's row filters, column masks, and ABAC tags start applying *automatically* — no app-side code change.

**Implementation pattern in this project**

1. Use the **shared `demo` catalog** (pre-existing — provisioned once by a metastore admin; operators never create it) plus **per-operator schemas** (`demo.nyctaxi_${monogram}` for taxi data, `demo.knowledge_assistant_${monogram}` for the document corpus). Operators only need `USE CATALOG` + `CREATE SCHEMA` on `demo` — `CREATE_CATALOG ON METASTORE` is never required. Schemas are the unit of organisation; tables / views / volumes hang off them.
2. Lift raw data once into a managed table inside the catalog (`trips_raw`), then build *curated views* on top with friendly column names + comments (`v_trips_genie`). The view is what the user-facing analytics consume — Genie, the dashboard, the Streamlit table page all read it. Comments on the columns become Genie's vocabulary.
3. Drop unstructured assets (PDFs, images, documents) into UC **volumes** rather than the lakehouse filesystem. Volumes carry the same `GRANT/REVOKE` model and are the canonical source for Knowledge Assistant ingestion.
4. Capture *what DAB has resource types for* as bundle resources — schemas, volumes, grants, the Lakebase instance / catalog / synced table, the AI/BI dashboard, the App and its resource bindings. The rest (tables, views, PDF uploads, Agent Bricks artefacts) is split between an imperative bootstrap script and the Agent Bricks UI / API. See Chapter 5 for the full split.

---

## Chapter 4 · Application Architecture & Shared Bootstrap

Every Streamlit page in the app does three things before any business logic: configure the page, render the brand, render the user badge. Repeating that boilerplate per page is how multipage Streamlit apps drift.

**The pattern** — a single `init_page(page_title=...)` function in `utils.py` that runs:

1. `st.set_page_config(...)` — the only `set_page_config` call in the codebase.
2. `st.logo(...)` with the Databricks lockup + symbol — so the sidebar branding is identical everywhere.
3. A small "Signed in as" badge inferred from the forwarded user-email header.

Every page's first line is `init_page("Page Name")`. Adding a new page is one import and one call.

**Why we didn't add a parallel `apply_branding()` helper:** the Streamlit-styling skill that informs this project is explicit that a second branding bootstrap drifts over time (one place updates fonts, the other doesn't). One bootstrap, one place to change.

**Design system** — the brand is encoded as Streamlit-native theme tokens, not custom CSS:

| Layer | What | Why |
|---|---|---|
| `.streamlit/config.toml` | Enables static file serving + points at the brand theme file. | Streamlit standard. |
| `.streamlit/brand-theme.toml` | All brand tokens — colours, fonts, sidebar, dark mode, chart palettes. | Native theming carries through to `st.metric`, `st.dataframe`, `st.line_chart` automatically. |
| `static/fonts/` | DM Sans + DM Mono `.ttf` files, registered via `[[theme.fontFaces]]`. | Self-hosted (no CDN dependency). Works in air-gapped deploys. |
| `assets/logos/` | Lockup + symbol SVGs in colour, navy, white, black variants. | `st.logo()` accepts any of them; the brand guide picks one per surface. |

This keeps the customisation surface small: change the colour anchors in one TOML, swap the SVGs in one folder, and every page picks it up. No per-page CSS, no per-page colour decisions.

---

## Chapter 5 · CI/CD — From Laptop to Workspace

**Databricks Asset Bundles (DAB)** are the deploy unit. A bundle is declarative YAML (`databricks.yml`) describing the workspace state you want: apps, schemas, volumes, dashboards, Lakebase instances, synced tables, plus the app-to-resource bindings that grant the app's SP access to each one.

**Why DAB over `databricks apps deploy`:**

- One command (`bundle deploy`) lands code + infrastructure + permissions in lockstep.
- `bundle destroy` removes everything the bundle owns — without touching shared catalogs / Genie spaces / KA tiles that other projects share.
- The same YAML promotes through `dev` → `staging` → `prod` targets, with per-target variable overrides.
- Terraform under the hood means resource dependencies are explicit (which surfaces issues like the catalog-before-synced-table ordering that we hit and documented).

**Why GitHub Actions (rather than manual `bundle deploy` from a laptop):**

- The deploy identity is the **app service principal**, not a developer's personal token. Auditable, scoped, revocable.
- The same workflow that runs `bundle deploy` also runs `bundle validate` on every pull request — broken YAML can't reach `main`.
- Public repo: secrets live as **Environment secrets** (masked in logs), the `dev` Environment can require a one-click reviewer approval, and the deployment-branch rule restricts production deploys to `main`.

**Auth path** — two supported flavours, both documented:

| Path A — GitHub OIDC | Path B — Client secret (this project ships path B) |
|---|---|
| No long-lived secret in GitHub | Stores `DATABRICKS_CLIENT_SECRET` as a GitHub Environment secret |
| Requires a Databricks federation policy on the service principal | One PATCH on the serving endpoints — no federation policy |
| Fork-PR safe; rotates by trust-policy update | Rotates by manually rotating the secret |
| Production-recommended | Faster bootstrap, especially on Azure workspaces where account-level federation isn't pre-configured |

**Implementation pattern**

1. **One CI workflow** (`ci.yml`) that runs on every PR: `uv sync --frozen` + `py_compile` on every page. No Databricks calls, no auth.
2. **One deploy workflow** (`deploy.yml`) that runs on push-to-`main` + manual dispatch, routed through a `dev` GitHub Environment. Inside the Environment, three protection rules: `main` only / required reviewer / optional wait timer.
3. The deploy workflow chains `bundle validate → bundle deploy → bundle run streamlit-demo`. `bundle deploy` does *not* restart the app — `bundle run` does. Forgetting that step is the single most common cause of "I deployed but I don't see my change".

### Three layers of provisioning — what the bundle owns vs. what stays manual

A working Databricks Apps build typically has *three* provisioning layers, each suited to a different kind of resource:

| Layer | What it owns | Why |
|---|---|---|
| **DAB (`databricks.yml`)** | UC schemas, volumes, grants on those; Lakebase instance + UC catalog + synced table; the AI/BI dashboard (sourced from `dashboards/<name>.lvdash.json`); the App + all resource bindings + permissions. | Declarative, idempotent, repeatable across `dev` / `staging` / `prod` targets. `bundle destroy` reverses it. |
| **Bootstrap script (`scripts/bootstrap.py`)** | Tables, views, primary-key constraints, `ANALYZE TABLE`, column comments, PDF uploads to the volume. | DAB has **no `tables:` / `views:` resource type** today. A Python script using `databricks-sql-connector` + `WorkspaceClient` runs the DDL once after `bundle deploy`. |
| **Agent Bricks UI / API** | The Genie Space, the Knowledge Assistant + its knowledge source, the Multi-Agent Supervisor + its routing examples. | Agent Bricks artefacts are **not in the DAB resource schema yet** (preview). Create via UI or the dedicated CLI subcommands (`databricks knowledge-assistants …`, `databricks supervisor-agents …`). |

There's also a fourth, *one-off* layer: **Postgres-side `GRANT`s** on the Lakebase synced table. DAB binds the database to the app and provisions a Postgres role for the app SP, but `GRANT SELECT ON TABLE …` runs *inside Postgres* — outside DAB's reach. Document the SQL in the relevant plan; run it once per (table, role) pair.

**Why this split is worth knowing as a pattern:** it tells you where to put the next piece of state. If DAB has a resource type for it, declare it in the bundle. If it's a tabular `CREATE TABLE` / `INSERT` / `ALTER TABLE`, put it in the bootstrap script. If it's a managed-AI artefact, create it once in the UI or via the CLI and bind it to the app via the bundle. Re-deploys stay clean because the layers don't overlap.

---

## Chapter 6 · Capability 1 — UC Analytics via SQL Warehouse

**The Sample Data page** is the simplest capability: read a Unity Catalog view, render a paginated table with sidebar filters and headline metrics.

**Why it matters as a starter pattern:** it's the bread-and-butter of internal-data Streamlit apps. Almost every real-world internal app starts as "let me view this table with some filters". Getting the OBO + caching + filter patterns right here is what scales to dozens of pages later.

**Why we read a *curated view* rather than a raw table:** the view exposes business-friendly column names (`pickup_ts`, `fare_amount_usd`, `valid_trip`) with UC comments, derives helpers (`route`, `duration_minutes`, `pickup_day_of_week`), and is the same object both Genie and the BI dashboard consume. One curated UC object underpins three user-facing capabilities — the brand of "lakehouse" in action.

**Implementation pattern**

1. **SQL Warehouse** — Pro or Serverless. The bundle declares it as an app resource binding (`apps.streamlit-demo.resources.sql-warehouse`), so `bundle deploy` automatically grants the App SP `CAN_USE` — no manual "Apps UI → Add resource" step. Capacity matters less than warm-up: serverless cold starts can add 1–2 seconds to the first query.
2. **`sql_conn()` helper in `utils.py`** — opens a fresh `databricks.sql.connect(...)` per call, passing the forwarded user token (`X-Forwarded-Access-Token`) as the access token. Returns a context-managed connection so each query cleans itself up.
3. **The view-level `SELECT` grant** lives in `scripts/bootstrap.py` because the view itself is bootstrap-script-owned (DAB doesn't have a `views:` resource type). The schema-level `USE_SCHEMA` is bundle-owned via the `grants:` block on the schema resource. Together they cover the access path.
4. **Per-session caching, not `st.cache_data`** — tables are per-user; OBO means every user sees a different slice. `st.cache_data` is process-global and would leak rows between users. Stash the DataFrame in `st.session_state` on first load, with a "Refresh data" button that clears it.
5. **Sidebar filters apply client-side** — once a slice is in pandas, filter changes don't re-query the warehouse. Saves cost and keeps interactions snappy.

**Watch for**

- The default `streamlit` advice (`st.cache_data` on the load function) is wrong for OBO-shaped apps. Use `st.session_state`.
- Don't `SELECT *` on production tables — name columns explicitly so the page survives upstream schema changes.
- The forwarded user token is short-lived (~1 hour). For long sessions, the per-call `sql_conn()` pattern just mints a fresh one on the next query.

---

## Chapter 7 · Capability 2 — OLTP-Shaped Serving via Lakebase

**Lakebase** is Databricks' serverless PostgreSQL service for OLTP workloads. Synced tables stream UC Delta data into a Postgres replica that an app can query with sub-second latency through standard `psycopg`.

**Why this matters:** SQL warehouses are optimised for analytic queries (scan large datasets, aggregate, return summaries). They're not the right shape for OLTP-style point lookups — fetching one row by ID, joining a handful of dimension tables, returning in <100ms for an interactive widget. Lakebase fills that gap with PostgreSQL semantics over the same governed data.

**Why a *synced* table rather than a direct UC query:** the same operational data lives in two shapes — the analytic Delta original (for Genie, dashboards, the warehouse) and the OLTP Postgres replica (for the Streamlit page's interactive widgets). Databricks runs the sync; the app never writes back, which preserves the analytic table as the source of truth.

**Why the *legacy `database_instances` DAB schema* still works in 2026+:** new Lakebase instances created in 2026 are Autoscale under the hood, but the legacy DAB resource shape (`database_instances` + `database_catalogs` + `synced_database_tables` + `apps.resources.database`) remains backward-compatible. That gives us a fully declarative bundle: one `databricks bundle deploy` creates the instance, registers it as a UC catalog, defines the synced table, and binds it to the app.

**Implementation pattern**

1. **Materialise a syncable source** — `synced_database_tables` requires a Delta table with a primary key. Views don't have PKs. We add a thin layer: `demo.nyctaxi.trips_for_sync` = the curated view + a `ROW_NUMBER()` surrogate `trip_id` + `NOT NULL` + `PRIMARY KEY` constraints. Created by `scripts/bootstrap.py` (DAB has no `tables:` resource type).
2. **Declare three resources in the bundle** — `database_instances.lakebase` (the instance), `database_catalogs.lakebase_catalog` (the UC registration), `synced_database_tables.trips_synced` (the sync itself, in `SNAPSHOT` mode for the simplest semantics). Sync modes are `SNAPSHOT` (whole-table copy on trigger), `TRIGGERED` (incremental, requires CDF), and `CONTINUOUS` (streaming). SNAPSHOT is the minimum-friction default. `bundle deploy` (re)creates all three idempotently.
3. **Bind the database to the app** via the app's `resources.database` block in the same bundle. Databricks injects `PGHOST`, `PGDATABASE`, `PGPORT`, `PGSSLMODE`, `PGUSER` into the runtime and creates a Postgres role for the app SP with `CONNECT` + `CREATE`.
4. **Run one set of `GRANT`s in the Lakebase SQL editor** — the bundle binding gets the SP into Postgres but not onto specific tables. One-off `GRANT USAGE ON SCHEMA <s>` + `GRANT SELECT ON TABLE <s>.<t>` per table, executed by the schema owner. This is the fourth (Postgres-side) layer of provisioning — DAB has no way to run SQL inside the synced Postgres database.
5. **Build a connection pool in the Streamlit page** with a `psycopg.Connection` subclass that mints a fresh OAuth token on every new connection. Lakebase OAuth tokens last ~1 hour; pooling with `max_lifetime=1800` recycles connections well before tokens expire.

**Watch for**

- A bundle-side gotcha that bit us once and is now in the plan: `synced_database_tables.name` must reference `${resources.database_catalogs.<key>.name}`, not the variable `${var.lakebase_catalog_name}`. Both produce the same string, but only the resource reference creates a Terraform dependency edge so the catalog is created *before* the synced table.
- `bundle destroy` removes the Lakebase instance and the synced data. Worth being explicit about when running it in a shared workspace.

---

## Chapter 8 · Capability 3 — Embedded AI/BI Dashboard

**AI/BI Dashboards** are Databricks' native, SQL-backed visualisation tool — built directly on Unity Catalog with zero data movement. Six datasets + thirteen widgets render in a 12-column responsive grid.

**Why embed in Streamlit at all** (rather than send users to the dashboard URL directly): the user is already in the app. Switching tabs / windows breaks the workflow. The dashboard is one page of seven that need to feel like one product.

**Why an embedded dashboard rather than a custom Plotly page in Streamlit:**

- **Native filters, drill-down, "ask Genie" button, comments, share, export** — all of that is built into AI/BI for free. Replicating it in Streamlit is many hundreds of lines of code that has to be maintained.
- **Editor / consumer split** — analysts edit the dashboard in the AI/BI workspace UI without touching the app. The Streamlit app just embeds whatever's currently published.
- **One source of truth for the visuals.** The same dashboard can be embedded in multiple apps, sent as a scheduled snapshot, or opened standalone in the Databricks UI.

**Implementation pattern**

1. **Test every dataset query first.** Each widget is bound to a dataset (one SQL query, pre-aggregated). Errors in the SQL surface only at widget-render time as opaque "Invalid widget definition" boxes. Run each query through `execute_sql` against the chosen warehouse before building the JSON.
2. **Build the dashboard once** — six datasets and thirteen widgets across a layout that fills a 12-column grid with no gaps. Counters are version 2 with `disaggregated:true`; bar/line charts are version 3. Build via the AI/BI UI or programmatically via `manage_dashboard(action="create_or_update", …)`.
3. **Commit the dashboard as source** — export the dashboard to `dashboards/<name>.lvdash.json` and check it into the repo. Then declare it as a bundle resource:
   ```yaml
   resources:
     dashboards:
       nyc_taxi_dashboard:
         display_name: NYC Taxi Trips Dashboard
         file_path: dashboards/nyc_taxi_dashboard.lvdash.json
         parent_path: ${var.dashboard_parent_path}
         warehouse_id: ${var.sql_warehouse_id}
   ```
   `bundle deploy` now (re)materialises the dashboard in the workspace from the file. Editing the JSON in the repo, committing, and redeploying is the supported update loop — no more "edit in UI, hope nobody re-deploys and overwrites it". Designers who prefer the AI/BI editor can still edit in-place, export back to `.lvdash.json`, and commit.
4. **Publish with `embed_credentials=true`** — visuals run with the publisher's identity, so end users only need to *see* the dashboard URL inside the workspace; they don't need direct UC `SELECT` on the source view. Switch to `embed_credentials=false` when you want UC row filters / column masks to apply per viewer.
5. **Streamlit page** is fifteen lines: `init_page` + `streamlit.components.v1.iframe(src=DASHBOARD_EMBED_URL, height=1100)`. The URL pattern is `<workspace>/embed/dashboardsv3/<id>` — the *embed* path, not the editor path. The ID is captured from `bundle summary` output or the dashboard's workspace URL.

**Watch for**

- The Streamlit `st.iframe(...)` API does not exist. Use `streamlit.components.v1.iframe`.
- Dashboards require a Pro or Serverless warehouse — Classic isn't supported.
- After editing the dashboard, re-publishing is what propagates changes to embedded surfaces.

---

## Chapter 9 · Capability 4 — Conversational Analytics via Genie

**AI/BI Genie** translates natural-language questions into SQL against Unity Catalog data. It's not "ChatGPT for your data" — it's a **compound AI system**: an intent parser, a retrieval agent over a curated *Knowledge Store* (synonyms, value dictionaries, example SQL, business-rule instructions), a SQL generator, and a verification agent. The accuracy comes from the curated metadata, not from the underlying model alone.

**Why two variants in this project (iframe + native):** the same Genie space, two different user experiences.

| Variant | When to choose |
|---|---|
| **Iframe** (`/embed/genie/rooms/<id>`) | Zero-maintenance, full workspace Genie UI, viewer's own permissions apply, follows the workspace's Genie improvements automatically. |
| **Native** (Conversation API + Streamlit chat) | Brand-consistent theming, custom sidebar prompts, programmatic access to the generated SQL + result DataFrame for downstream use. |

Same Genie space — different surfaces. We documented both because the choice is a per-app trade-off, not a per-product one.

**Why we built a *curated* Genie space (not pointed it at the raw table):**

- The raw `samples.nyctaxi.trips` table uses cryptic column names (`tpep_pickup_datetime`, `fare_amount`) and integer ZIP codes. Genie's accuracy depends on metadata quality.
- The curated view `demo.nyctaxi.v_trips_genie` exposes business-friendly columns (`pickup_ts`, `fare_amount_usd`, `time_of_day`, `valid_trip`), each with a UC comment that Genie picks up as vocabulary.
- Adding `synonyms`, `SQL expressions` (for reusable measures), and *example SQL* + *trusted parameterised queries* in the Genie config raises benchmark accuracy materially.

**Implementation pattern**

1. **Stage the source** — inside the shared `demo` catalog, create a per-operator schema (`demo.nyctaxi_${monogram}`), lift the source table, add comments, and build a curated view. The view, not the raw table, is what Genie sees.
2. **Create the Genie space** — `Workspace → Agents → Create Agent → Genie Space` (UI) or `create_or_update_genie(...)` via MCP. Attach a single curated object (or a small set — Databricks recommends starting with 5 or fewer).
3. **Configure the Knowledge Store** — synonyms per column, prompt/entity matching for string columns, text instructions for refusal posture, SQL expressions for reusable filters and measures, example SQL for common questions, trusted parameterised queries for templated metrics.
4. **Benchmark** — Databricks recommends 10–20 golden queries; production threshold is 85%+ accuracy. The plan ships a five-prompt minimum set.
5. **Embed or call** — pick iframe (zero code) or native (Conversation API). For native, the app's service principal needs explicit `CAN_RUN` on the Genie space ACL **plus** UC grants along the source-view path. The Genie Space itself is created outside DAB (Agent Bricks isn't in the bundle schema yet), but the **app-side `CAN_RUN` binding** is bundle-owned via `apps.streamlit-demo.resources.genie-space` — so once you've captured the Genie space ID, `bundle deploy` grants the SP automatically.

**Watch for**

- Genie inherits the caller's UC permissions. With native + App SP, every user sees the same data; with iframe + viewer identity, row filters and column masks apply per user.
- "Last month" relative to a static dataset means *the latest month in the data*, not `CURRENT_DATE` minus a month. The Knowledge Store's text instructions should tell Genie this explicitly when the dataset is fixed (as in this demo).

---

## Chapter 10 · Capability 5 — Document Q&A via Knowledge Assistant

**Agent Bricks' Knowledge Assistant** is a managed RAG endpoint over governed documents. You upload PDFs / Markdown / Word / PowerPoint files into a UC volume, point Knowledge Assistant at the volume, and it runs the entire RAG stack — chunking, embedding, indexing, retrieval, citation extraction — and exposes the result as a serving endpoint.

**Why managed RAG, not a hand-rolled stack:**

- A hand-rolled RAG needs a chunker, an embedder, a vector index, a retrieval prompt, a re-ranker, a citation extractor, and an evaluation loop. Each of those is its own decision tree, its own dependency, and its own operational concern.
- Knowledge Assistant ships all of that, governed by UC, with citations as first-class outputs. SME guidelines and labelled examples are a UI workflow, not a notebook.
- Trade-off: less control. You can't (today) plug in a custom re-ranker or hybrid retrieval. If you need that, you go custom — but for the common case of "answer questions about official docs with citations", managed RAG ships in an afternoon.

**Why governed source documents matter:** Knowledge Assistant inherits UC permissions on the source volume. The Streamlit app's service principal needs `READ_VOLUME` on the volume (so ingestion can read the PDFs) and `CAN_QUERY` on the serving endpoint (so the app can ask questions). Adding a new viewer is two `GRANT`s, not a "talk to IT about S3 bucket policy".

**Implementation pattern**

1. **Create a UC schema + volume** for the corpus — both bundle-owned via `resources.schemas.knowledge_assistant` + `resources.volumes.ka_docs`. Volumes are the canonical storage for non-tabular files in Databricks — the same governance applies as for tables.
2. **Upload the documents** via `scripts/bootstrap.py` (DAB has no volume-file resource type; uploads are imperative). Supported types: PDF, Markdown, plain text, DOCX, PPTX. Files larger than 50 MB are skipped during ingestion.
3. **Create the Knowledge Assistant** — `Workspace → Agents → Create Agent → Knowledge Assistant`, or via CLI / MCP `manage_ka`. Provide a display name, description, and **instructions** (the system prompt — refusal posture, citation requirements, conflict-resolution rules). Created outside DAB; the bundle doesn't own it.
4. **Attach a knowledge source** of type `files` pointing at the volume. Ingestion takes 5–15 minutes for a small corpus.
5. **Bind the endpoint to the app** via `apps.streamlit-demo.resources.ka-endpoint` in the bundle — `bundle deploy` grants the App SP `CAN_QUERY`. Capture the endpoint name once (e.g. `ka-<hash>-endpoint`) and feed it to the bundle variable.
6. **Call from Streamlit** — `requests.post(...)` to `/serving-endpoints/<name>/invocations` with an OpenAI Responses-shaped body: `{"input": [{"role": "user", "content": prompt}]}`. The response's `output[].content[].annotations[]` carries `file_citation` entries that render as bullet links in the UI.

**Watch for**

- Knowledge Assistant endpoints use the OpenAI Responses API shape (`input`), not the Chat Completions shape (`messages`). The SDK's `serving_endpoints.query(...)` helper only supports `messages` — call REST directly.
- `custom_outputs.sources_used` is the most useful signal in the response: when it's `false`, either the assistant refused (out-of-scope question) *or* ingestion is still in progress. The page should surface that state distinctly from "no answer".
- One creator-only operation: only the Knowledge Assistant's creator can trigger sync / manage sources. Plan permissions accordingly.

---

## Chapter 11 · Capability 6 — Multi-Agent Orchestration via Supervisor Agent

**Multi-Agent Supervisor** is the most ambitious capability of the demo. It orchestrates multiple specialist subagents — a Genie space, a Knowledge Assistant, optionally custom RAG agents — and picks the right one (or several) per question. For cross-domain questions it fans out to multiple subagents and synthesises a single answer with sections per source.

**Why this matters as a category:** real internal users don't think in terms of "this question is for the BI tool, this one is for the policy chatbot". They ask one question and want one answer. A supervisor agent is the layer that maps natural-language questions onto the right specialist — without app-side `if/else` routing code.

**Why a managed supervisor instead of writing routing logic in Python:**

- Routing rules live with the agent in the workspace, not scattered across app code. Adding a third subagent is a workspace-side edit.
- SME feedback loops (rate this answer, this routing was wrong, here's the right routing) feed back into Agent Bricks' continuous improvement workflow.
- The supervisor enforces access control — if a user can't access one of the subagents, it routes around it transparently.

**Implementation pattern**

1. **Build the subagents first.** A supervisor is only as good as its constituents. The Genie space and Knowledge Assistant need to be standalone-good before they're plugged in.
2. **Create the supervisor** via MCP `manage_mas` (or the CLI `supervisor-agents create-supervisor-agent`). Pass:
   - The **subagent list** — each entry has a name, a long *description that drives routing* (the supervisor reads it to decide where to delegate), and exactly one of `genie_space_id` / `ka_tile_id` / `endpoint_name` / `uc_function_name` / `connection_name`.
   - **Routing + synthesis instructions** — the system prompt for the supervisor itself: when to call one specialist vs. both, how to format mixed-domain answers, how to handle conflicts between specialists.
   - **SME examples** (5+) — `{question, guideline}` pairs that ground the routing behaviour. These improve quality more than tuning instructions alone.
3. **Grant the app SP `CAN_QUERY` on the supervisor endpoint AND on every subagent endpoint** — the supervisor cascades calls in the caller's identity. Missing any one grant turns a fan-out question into a partial / 403 answer. All three bindings (supervisor endpoint, KA endpoint, Genie space) are bundle-owned under `apps.streamlit-demo.resources.*` — so once the three workspace artefacts exist and their IDs are in the bundle variables, `bundle deploy` provisions the SP's permissions in one shot.
4. **Page-side parsing.** The supervisor's response body is a *multi-turn trace*, not a single answer. `output[]` contains supervisor planning text, `<name>subagent</name>` boundary markers, each subagent's raw output, and finally the supervisor's synthesised reply. The page parses the trace, surfaces the final supervisor turn as the main answer, and tucks the intermediate steps into an expandable "Reasoning + tool calls" panel.

**Watch for**

- The 20-agent cap. The Agent Bricks UI lets you select more, but the limit is 20 per supervisor — design under it.
- Without the trace parser, the user sees `<name>...</name>` markers and intermediate tool outputs mixed with the answer. Parse, then surface.
- The supervisor description quality drives routing. Vague descriptions ("answers business questions") will route badly. Be specific about *what each subagent owns* and *what it does not* — see the supervisor instructions in the relevant plan.

---

## Chapter 12 · Cross-Cutting — Auth & Permissions Model

There are three identities to keep straight in any Databricks-Apps build:

| Identity | What it is | What it does |
|---|---|---|
| **The signed-in user** | The Databricks-SSO user opening the app in a browser. | Carries UC permissions, row filters, column masks. Available to the app as `X-Forwarded-Access-Token` if user authorization is enabled (OBO). |
| **The app's service principal** | An identity Databricks auto-creates per app. Available as `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET` env vars. | Calls APIs in the app's own name. Holds endpoint `CAN_QUERY` and resource grants. |
| **The deploy service principal** | A separate SP used by GitHub Actions (in this build) to run `bundle deploy`. | `CAN_MANAGE` on the app + the resources the bundle owns. |

**Which one to use when:**

- **OBO (forwarded user token)** for any feature where the user's own permissions should govern the result — UC-table viewers, Genie iframe, anywhere row-level or column-level access matters.
- **App SP** for managed-RAG calls (Knowledge Assistant) and supervisor calls. The endpoints have their own permissions model; the SP is the caller of record; viewers see identical results.
- **Deploy SP** for CI/CD only. Should *not* be the runtime identity.

**Why we ship App SP everywhere in this build (rather than OBO):** simpler bootstrap on a public-repo + Azure workspace where account-level federation isn't pre-configured. OBO is documented as the production upgrade path in two plans (CI/CD and Supervisor); migrating later is adding `user_api_scopes` to the bundle + swapping one helper call per page.

**The permission audit before any agent call:** every agentic page in this project needs three grants in place, *all of them on the App SP*:

1. **App layer** — `CAN_QUERY` on the relevant serving endpoint (KA endpoint or Supervisor endpoint).
2. **Genie layer** — `CAN_RUN` on the Genie space (for the Genie-native page or any supervisor that includes Genie).
3. **UC layer** — `USE_CATALOG` + `USE_SCHEMA` + `SELECT` along the source-view path.

**Where each grant comes from now that the bundle does most of the heavy lifting:**

| Grant | Owner |
|---|---|
| App SP → serving endpoints (`CAN_QUERY`) | **Bundle** via `apps.streamlit-demo.resources.<key>` bindings |
| App SP → Genie Space (`CAN_RUN`) | **Bundle** via `apps.streamlit-demo.resources.genie-space` |
| App SP → SQL Warehouse (`CAN_USE`) | **Bundle** via `apps.streamlit-demo.resources.sql-warehouse` |
| App SP → UC schema (`USE_SCHEMA`) | **Bundle** via `resources.schemas.<name>.grants` |
| App SP → UC volume (`READ_VOLUME`) | **Bundle** via `resources.volumes.<name>.grants` |
| App SP → specific table / view (`SELECT`) | **`scripts/bootstrap.py`** — view-level grants depend on the view existing, and the view is bootstrap-script-owned |
| App SP → Postgres table (`SELECT`) | **Manual SQL** in the Lakebase editor — DAB can't run SQL inside Postgres |
| End users → app (`CAN_USE`) | **Bundle** via `apps.streamlit-demo.permissions` |

Missing any of these is the single most common diagnostic in this build. The takeaway is that the bundle owns *most* of the matrix now — when something fails with a permission error, the first check is which row above isn't in place yet, and whether it's a bundle issue, a bootstrap-script issue, or one of the two "manual" rows.

**How those three grants are applied today:** all three are declared as **app resource bindings** in `databricks.yml` (`apps.streamlit-demo.resources.{sql-warehouse, lakebase-db, genie-space, ka-endpoint, supervisor-endpoint}`). `bundle deploy` reconciles them on every run; `bundle destroy` revokes them cleanly. The manual `databricks api patch /api/2.0/permissions/...` flow that earlier drafts of these plans documented is now an **optional alternative** for workspaces without DAB tooling — every plan still carries the imperative recipe in case you need it.

---

## Chapter 13 · Lessons Learned — Patterns Worth Internalising

Some of these are obvious in retrospect; some only become visible after a deploy fails in a specific way. All of them are documented in the relevant plan's *"What to avoid"* section so the next implementer doesn't pay the same cost.

**Auth shape**

- KA + Supervisor endpoints speak the **OpenAI Responses API** (`{"input": [...]}`), not Chat Completions (`{"messages": [...]}`). The SDK's `serving_endpoints.query(...)` only supports the latter — call REST directly for the former.
- The permissions PATCH path needs the **endpoint ID** (UUID), not the endpoint name. Look up the ID first; the name is for display only.

**Bundle / deploy**

- Terraform dependency edges come from *resource references*, not variables that produce the same string. When one resource needs another to exist first, reference it as `${resources.<type>.<key>.<field>}`.
- `bundle deploy` does not restart the app process. Always follow with `bundle run <app-name>`.

**Data shape**

- Lakebase synced tables require a Delta table with a primary key. Views can't have PKs — materialise a thin shim table with a synthetic surrogate key.
- Synced tables in `SNAPSHOT` mode don't need Change Data Feed. `TRIGGERED` and `CONTINUOUS` do.

**Application shape**

- `st.cache_data` is process-global and leaks across users. Use `st.session_state` for any data that depends on the caller (OBO results, chat history).
- Don't nest `st.chat_message` contexts. Streamlit raises. Render history at top level *before* opening the new turn's contexts.
- The Streamlit `st.iframe(...)` API does not exist. Use `streamlit.components.v1.iframe`.

**Public-repo hygiene**

- Personal absolute paths (`/Users/<name>/...`) sneak in via IDE configs, MCP configs, agent kits. The trick is to ship *template* files (`*.template`) and gitignore the live names.
- Even non-sensitive values like the workspace host are best stored as Environment **secrets** rather than variables on a public repo — secrets get masked in workflow logs automatically.

---

## Chapter 14 · Roadmap — What's Next

**Production-hardening (the immediate next pass):**

- **Switch CI/CD to GitHub OIDC** — kill the long-lived `DATABRICKS_CLIENT_SECRET`. Requires a one-time federation policy on the deploy SP; everything else is a three-line workflow patch.
- **Switch app auth to OBO** — per-user UC permissions on the Genie data; row filters and column masks apply automatically. Requires `user_api_scopes: [serving.serving-endpoints, dashboards.genie, sql]` on the app, and swapping `workspace_client_app()` for `workspace_client_obo()` in the pages that should be user-scoped.
- **Feedback capture** — add 👍 / 👎 buttons under each chat answer that write into a Delta table for SME review. Feeds Agent Bricks' continuous-improvement workflow.
- **MLflow trace IDs** in the supervisor page — `extra_headers={"x-mlflow-return-trace-id": "true"}` on the endpoint call surfaces a trace ID; store it with the feedback row for end-to-end observability.

**Capability expansion:**

- **Custom RAG subagent** under the supervisor — for cases where Knowledge Assistant's managed retrieval isn't enough (custom metadata filters, hybrid retrieval, per-tenant filtering). Best built today as a Databricks Apps custom agent (Apps now hosts agents directly, not just frontends).
- **Additional Genie spaces** for other business domains — the supervisor stays the same shape; adding a subagent is a workspace-side change.
- **App telemetry (Public Preview)** — OpenTelemetry-driven app logs and metrics persisted to UC tables.
- **Load testing** — Databricks publishes a Locust-based load-testing pattern for agent endpoints. Establish QPS / latency / failure-rate thresholds before rolling beyond pilots.

**Fork-and-rebrand workflow (the strategic next step):**

Because every step is captured as a standalone plan, a customer engagement can fork this repo, swap the data (their catalog instead of `demo.nyctaxi_${monogram}`, their PDFs instead of Northwind's), and re-run each plan via Claude Code. The brand-theme and logos swap in via the design-system plan. End result: a customer-branded, customer-data demo app in a working day, not a sprint.

---

## Chapter 15 · Appendix — The Plan Ladder as Runbook

The `docs/plans/` folder is the operational documentation for this project. Each plan is **standalone** — readable end-to-end without flipping between files — and follows the same five-part structure:

1. **Parameters to set** (with a fill-in worksheet for the deployment's actual values).
2. **Overview** (what the feature does, why this approach, end-to-end flow).
3. **Databricks-side prerequisites** (the workspace setup, with both a Claude Code prompt that drives it automatically and the manual commands for hands-on use).
4. **DAB updates** (the bundle diffs).
5. **Source code updates** (with the full page source inlined so the plan can be replayed without referencing `pages/`).

Each plan finishes with a **Verification** section (compile, validate, deploy, smoke test in the browser, plus negative tests that prove the permissions are correctly scoped) and a **What to avoid** section (the gotchas we hit, anchored to a specific symptom).

| Plan | Sets up |
|---|---|
| `0_A_initial_setup.md` | App + bundle + utils + `uv` + initial DAB skeleton + ai-dev-kit local tooling |
| `0_B_design_system.md` | Databricks-branded Streamlit theme + DM Sans / DM Mono + logo variants |
| `0_C_github_actions.md` | CI + deploy workflows, OIDC vs client-secret paths, public-repo hardening |
| `0_D_genie_setup.md` | Curated UC catalog / schema / view + Genie Space configuration + benchmarks |
| `1_sample_data_page.md` | UC table browser with OBO + sidebar filters + headline metrics |
| `2_lakebase_sync_page.md` | Lakebase synced table + psycopg pool with OAuth-token rotation |
| `3_dashboard_embed_page.md` | AI/BI dashboard built via JSON + iframe embed |
| `4_genie_iframe_page.md` | Genie iframe variant (viewer's identity) |
| `5_genie_native_page.md` | Genie native chat via Conversation API (App SP) |
| `6_knowledge_assistant_page.md` | Knowledge Assistant chat with citations + ingestion handling |
| `7_supervisor_page.md` | Multi-Agent Supervisor with trace parser + reasoning expander |
| `sum.md` | This summary |

To re-create the demo against your own data, work down the ladder in order. The first four (`0_*`) are workspace bootstrap; the rest (`1`–`7`) each add one page on top.

---

## Chapter 16 · The Pitch in Two Lines

A Databricks-native, governed, multi-page Streamlit app that demonstrates **the full data + AI stack** — Unity Catalog, SQL Warehouses, Lakebase, AI/BI Dashboards, Genie, Knowledge Assistant, and Multi-Agent Supervisor — wired the way Databricks intends, deployed via Asset Bundles, brand-consistent via native theming, and shipped with CI/CD on GitHub Actions.

**For engineering:** every step is documented, every gotcha is in writing, every auth/permission boundary is named, and the same plans drive Claude Code so the heavy lifting is automatable.

**For executives:** one repo, one design system, one deploy pipeline — and capabilities spanning structured analytics, OLTP serving, BI, conversational data, document Q&A, and agent orchestration without bespoke glue for any of them.
