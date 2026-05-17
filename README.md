# Databricks Apps Streamlit Starter

A production-ready starter template for building Streamlit apps on Databricks Apps platform.

> **Built for Vibe Coding**: This project is optimized for AI-assisted development with [Claude Code](https://claude.com/code), [OpenAI Codex](https://openai.com/index/openai-codex/), [GitHub Copilot](https://github.com/features/copilot), or similar editors. Includes comprehensive context in `CLAUDE.md`, inline documentation, and cookbook examples to accelerate development. MCP batteries included, like Context7, ref.tools, GitHub MCP.

## Features

- **Databricks-branded look-and-feel out of the box.** DM Sans + DM Mono, Databricks colour anchors, dark mode, sidebar palette, and chart palettes — all defined as Streamlit theme tokens in `.streamlit/brand-theme.toml`. See [`DESIGN-SYSTEM.md`](DESIGN-SYSTEM.md) for the brand guide.
- **One-call page bootstrap.** `utils.init_page(page_title=...)` wires `st.set_page_config()`, `st.logo()`, and the signed-in user badge — no per-page drift.
- **OBO authentication.** Forwarded user token via `X-Forwarded-Access-Token` flows into `sql_conn()` and `workspace_client_obo()`; Unity Catalog row/column policies are enforced for the signed-in user automatically.
- **`uv`-managed.** `pyproject.toml` + `uv.lock` for fast, reproducible installs locally and on Databricks Apps.
- **Asset bundle deploys.** `databricks.yml` declares the App, permissions, and per-page resource bindings — `databricks bundle deploy -t dev` is the one-shot deploy.

_Add your app-specific features below as you build…_

## Local Development

The project uses [`uv`](https://docs.astral.sh/uv/) for Python dependency management (`pyproject.toml` + `uv.lock`). Three commands to a working local app:

```bash
# 1. Install uv if you don't have it (see https://docs.astral.sh/uv/)
uv --version

# 2. Install Python deps into a project-local .venv
uv sync

# 3. Run the Streamlit app
uv run streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501).

Notes:

- The home page (`app.py`) renders without any Databricks-side wiring. Pages under `pages/` that call `sql_conn()`, Genie, etc., need the corresponding env vars set in your shell (`SQL_WAREHOUSE_ID`, `UNITY_CATALOG_TABLE`, `GENIE_SPACE_ID`, ...) plus a way to inject the OBO `X-Forwarded-Access-Token` header. The Databricks Apps runtime sets all of this in production.
- For a higher-fidelity local run that mirrors the Databricks Apps runtime (resolves `valueFrom` resources, sets the same env vars, picks the entrypoint from `app.yaml`), use `databricks apps run-local` — see [DEPLOY.md § C](DEPLOY.md).
- Add new dependencies with `uv add <package>`. **Do not** create a `requirements.txt`; Databricks Apps gives it precedence over `pyproject.toml` and silently falls back to pip.

## Quick Start

### 1. Prerequisites

**Required:**
- Databricks workspace with Apps support

**Optional (depending on features you want to use):**

**Data Access:**
- SQL Warehouse (CAN USE permission) - for querying Delta tables
- Unity Catalog tables/volumes (SELECT/READ permissions) - for data operations
- OLTP database connection - for external database queries

**AI/ML:**
- Model Serving endpoint (CAN QUERY permission) - for ML inference
- Vector Search endpoint (CAN USE permission) - for similarity search
- Genie Space (CAN VIEW, CAN RUN permissions) - for AI chat

**Business Intelligence:**
- AI/BI Dashboard (CAN VIEW permission) - for embedding dashboards

**Workflows:**
- Job (CAN VIEW, CAN MANAGE RUN permissions) - for triggering workflows

**Compute:**
- Cluster (CAN ATTACH TO permission) - for data transformation at scale

**Governance:**
- External Connection (CAN USE permission) - for governed HTTP endpoints
- Secret Scope (READ permission) - for secure credential storage

### 2. Configure Environment

Edit `app.yaml` to configure resources and environment variables for the features you need:

```yaml
env:
  # Data Access
  - name: SQL_WAREHOUSE_ID
    valueFrom: sql-warehouse
  - name: UNITY_CATALOG_TABLE
    value: "main.default.my_table"
  - name: UNITY_CATALOG_VOLUME
    value: "main.default.my_volume"

  # AI/ML
  - name: MODEL_SERVING_ENDPOINT
    valueFrom: model-endpoint
  - name: VECTOR_SEARCH_ENDPOINT
    valueFrom: vector-search-endpoint
  - name: GENIE_SPACE_ID
    valueFrom: genie-space

  # Business Intelligence
  - name: DASHBOARD_EMBED_URL
    value: "https://<workspace-host>/embed/dashboardsv3/<dashboard-id>"

  # Workflows
  - name: JOB_ID
    valueFrom: workflow-job

  # Compute
  - name: CLUSTER_ID
    valueFrom: compute-cluster

  # Governance
  - name: EXTERNAL_CONNECTION_NAME
    valueFrom: external-connection
  - name: SECRET_SCOPE
    value: "my-secret-scope"
  - name: SECRET_KEY
    value: "my-api-key"
```

**Notes:**
- Use `valueFrom` for Databricks resources (binds to resource ID)
- Use `value` for direct values (URLs, table names, scope names)
- Only include the resources you actually need

### 3. Deploy to Databricks Apps

1. **Create a new Databricks App**:
   - Go to Databricks workspace → Apps → Create App
   - Choose "Streamlit" template
   - Connect this Git repository

2. **Add Resources** (only add what you need):

   **Data:**
   - SQL Warehouse → key: `sql-warehouse`

   **AI/ML:**
   - Model Serving Endpoint → key: `model-endpoint`
   - Vector Search Endpoint → key: `vector-search-endpoint`
   - Genie Space → key: `genie-space`

   **Workflows:**
   - Job → key: `workflow-job`

   **Compute:**
   - Cluster → key: `compute-cluster`

   **Governance:**
   - External Connection → key: `external-connection`
   - Secret Scope → add secret references directly in env vars

3. **Configure Authorization**:
   - Go to **Authorization** tab
   - Enable **User authorization**
   - Add required scopes:
     - `sql` (to query warehouses)
     - `dashboards.genie` (to use Genie)
     - `iam.current-user:read` (for user identity - usually enabled by default)

4. **Deploy**:
   - Click **Deploy**
   - Wait for build to complete
   - Open the app URL

## Architecture

### File Structure

```
.
├── app.py              # Main entrypoint with home page (calls init_page)
├── utils.py            # Shared helpers: init_page(), sql_conn(), workspace clients, …
├── pages/              # Page files (auto-discovered by Streamlit)
│   └── 0_empty.py
├── .streamlit/
│   ├── config.toml     # Enables static serving, points at brand-theme.toml
│   └── brand-theme.toml # Databricks brand tokens — colours, fonts, dark mode, sidebar
├── static/fonts/       # Self-hosted DM Sans + DM Mono (referenced by brand-theme.toml)
├── assets/logos/       # Databricks lockup / symbol SVGs used by st.logo() and favicon
├── app.yaml            # Runtime config + resource bindings
├── pyproject.toml      # Python deps + project metadata (uv-managed)
├── uv.lock             # Pinned dependency tree (commit; Databricks runs `uv sync`)
├── databricks.yml      # Databricks Asset Bundle (deploy via `databricks bundle deploy`)
├── DESIGN-SYSTEM.md    # Databricks brand guide for this Streamlit project
└── README.md           # This file
```

### Key Design Patterns

**On-Behalf-Of (OBO) Authentication**:
- Uses `st.context.headers['x-forwarded-access-token']` to get user token
- All SQL queries and Genie conversations run as the signed-in user
- UC row/column filters automatically apply

**Resource Configuration**:
- Resources (SQL Warehouse, Genie Space) are added via Databricks Apps UI
- IDs are injected as environment variables via `valueFrom` in `app.yaml`
- No hardcoded resource IDs in code

**Error Handling**:
- `get_env()` in `utils.py` checks for required environment variables
- Shows friendly error messages instead of crashes
- Gracefully handles missing permissions or resources

**Multipage Navigation**:
- Uses Streamlit's standard multipage structure with `pages/` directory
- Each page is a separate file for better organization
- Streamlit automatically discovers pages and creates navigation
- Page file names determine display order (e.g., `1_my_page.py`, `2_another_page.py`)

## Resources & Documentation

- [Databricks Apps Documentation](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/)
- [User Authorization & OBO](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth)
- [Streamlit Tutorial for Databricks](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/tutorial-streamlit)
- [Genie Conversation API](https://docs.databricks.com/aws/en/genie/conversation-api)
- [Databricks Apps Cookbook](https://apps-cookbook.dev/)
- [Streamlit Multipage Apps](https://docs.streamlit.io/develop/api-reference/navigation/st.page)

### Local Cookbook Reference

This repository includes the [Databricks Apps Cookbook](https://github.com/databricks-solutions/databricks-apps-cookbook) as a git submodule in the `cookbook/` directory. This provides local access to additional examples and patterns for various frameworks (Streamlit, Dash, FastAPI, Flask, Gradio).

To clone this repository with the cookbook submodule:
```bash
git clone --recurse-submodules https://github.com/your-org/your-repo.git
```

To update the cookbook submodule:
```bash
git submodule update --remote cookbook
```

## License

See [LICENSE](LICENSE) file.
