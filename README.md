# Databricks Apps Streamlit Starter

A production-ready starter template for building Streamlit apps on Databricks Apps platform.

> **Built for Vibe Coding**: This project is optimized for AI-assisted development with [Claude Code](https://claude.com/code), [OpenAI Codex](https://openai.com/index/openai-codex/), [GitHub Copilot](https://github.com/features/copilot), or similar editors. Includes comprehensive context in `CLAUDE.md`, inline documentation, and cookbook examples to accelerate development. MCP batteries included, like Context7, ref.tools, GitHub MCP.

## Features

_Add your app features here as you build..._

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
├── app.py              # Main entrypoint with home page
├── utils.py            # Shared utilities and connection builders
├── pages/              # Page files (auto-discovered by Streamlit)
│   ├── ...
├── app.yaml            # Runtime config + resource bindings
├── requirements.txt    # Python dependencies
└── README.md          # This file
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
