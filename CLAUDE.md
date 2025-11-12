# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Project Overview

This is a **starter template** for building multi-file Streamlit apps on **Databricks Apps** with on-behalf-of (OBO) user authentication.

**Key principle**: The app runs as the signed-in user, respecting Unity Catalog row/column policies.

**Common patterns you can implement**:
- Unity Catalog table viewer
- Genie AI chat interface
- Embedded AI/BI dashboard
- Custom data visualizations
- Interactive data editing

---

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (requires env vars or modification for local auth)
streamlit run app.py
```

---

## Architecture & Design Patterns

### Multi-File Structure
The app uses Streamlit's standard multipage layout:
- **`app.py`**: Main entrypoint with page config, logo, user badge, and home page content
- **`utils.py`**: Shared utilities (`get_env()`, `get_user_token()`, `render_sidebar()`, connection builders)
- **`pages/`**: Directory for page files that Streamlit auto-discovers:
  - `0_empty.py` - Template for creating new pages (included)
  - Add your own pages here (e.g., `1_my_page.py`, `2_another_page.py`)

**Navigation**: Streamlit automatically discovers and creates navigation from files in `pages/`. File names determine order and page names (e.g., `1_my_page.py` → "My page").

### Authentication Flow
1. **User authorization** must be enabled in Databricks Apps UI with scopes: `sql`, `dashboards.genie`, `iam.current-user:read`
2. User token extracted from `st.context.headers['X-Forwarded-Access-Token']` via `get_user_token()` in `utils.py`
3. Token passed to:
   - SQL connector: `WorkspaceClient(token=get_user_token(), auth_type="pat")`
   - Databricks SDK: Uses default `Config()` which picks up injected app credentials

**Critical**: The app uses **two auth modes**:
- **SQL queries**: Uses `Config().authenticate` (app-level credentials via `credentials_provider`)
- **Genie API calls**: Uses standard `WorkspaceClient()` (Genie handles OBO internally)

### Resource Configuration Pattern
Resources are **never hardcoded**. All resource IDs come from environment variables configured in `app.yaml`:

**Data Access:**
- `SQL_WAREHOUSE_ID` → `valueFrom: sql-warehouse` (for querying Delta tables)
- `UNITY_CATALOG_TABLE` → `value: "main.default.my_table"` (table name)
- `UNITY_CATALOG_VOLUME` → `value: "main.default.my_volume"` (volume path)
- `OLTP_CONNECTION_STRING` → from secret scope or direct value

**AI/ML:**
- `MODEL_SERVING_ENDPOINT` → `valueFrom: model-endpoint` (for ML inference)
- `VECTOR_SEARCH_ENDPOINT` → `valueFrom: vector-search-endpoint` (for similarity search)
- `GENIE_SPACE_ID` → `valueFrom: genie-space` (for AI chat)

**Business Intelligence:**
- `DASHBOARD_EMBED_URL` → `value: "https://..."` (from Dashboard → Share → Embed iframe)

**Workflows:**
- `JOB_ID` → `valueFrom: workflow-job` (for triggering jobs)

**Compute:**
- `CLUSTER_ID` → `valueFrom: compute-cluster` (for data transformation at scale)

**Governance:**
- `EXTERNAL_CONNECTION_NAME` → `valueFrom: external-connection` (for governed HTTP endpoints)
- `SECRET_SCOPE` → `value: "my-secret-scope"` (scope name)
- `SECRET_KEY` → `value: "my-api-key"` (key name)

**Pattern**: Use `valueFrom` for Databricks resources (binds to resource ID), use `value` for direct values (URLs, table names, scope names).

Use `get_env(name)` from `utils.py` to access env vars—it shows friendly errors and calls `st.stop()` instead of crashing.

### State Management
- **Session state**: Use `st.session_state` to persist data across page reruns (e.g., conversation IDs, user selections)
- **Sidebar**: Call `render_sidebar()` in every page to show logo and user badge consistently
- **Cross-page state**: Session state is shared across all pages in the app

### Genie API Integration Pattern
**IMPORTANT**: Always use `workspace_client()` (NOT `workspace_client_obo()`) for Genie API calls. Genie handles OBO authentication internally.

Follow this exact flow (based on official samples):
```python
from utils import workspace_client

# Get standard workspace client (Genie handles OBO internally)
w = workspace_client()

# Start conversation
conversation = w.genie.start_conversation_and_wait(space_id, prompt)
st.session_state.conversation_id = conversation.conversation_id

# Continue conversation
conversation = w.genie.create_message_and_wait(space_id, conversation_id, prompt)

# Extract results
for att in conversation.attachments:
    if att.text:
        st.markdown(att.text.content)
    elif att.query:
        stmt_id = conversation.query_result.statement_id
        result = w.statement_execution.get_statement(stmt_id)
        df = pd.DataFrame(result.result.data_array, columns=[...])
```

**Do not** nest `st.chat_message()` contexts—Streamlit will error.

**Quick prompts pattern**: To improve UX, show example prompts in the sidebar that users can click to prefill the chat:
```python
# Add example quick-prompts to sidebar
with st.sidebar:
    st.divider()
    st.markdown("#### Example prompts")
    st.caption("Click to send:")
    examples = [
        "Show sales by region for last 7 days",
        "Top 5 products by revenue this month",
        "Customer growth trend over last quarter",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True):
            st.session_state["_prefill"] = ex
```

---

## Deployment to Databricks Apps

### Prerequisites (Optional - add only what you need)

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

### Deployment Steps

1. **Add resources in Apps UI** (only add what you need):

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

2. **Configure authorization**:
   - Enable **User authorization**
   - Add required scopes:
     - `sql` (to query warehouses)
     - `dashboards.genie` (to use Genie)
     - `iam.current-user:read` (for user identity - usually enabled by default)

3. **Update `app.yaml`** with environment variables for the features you need:
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

4. **Deploy** via Databricks Apps UI or CLI:
   ```bash
   databricks apps deploy <app-name> --source-code-path /Workspace/<path>
   ```

---

## Common Modification Patterns

### Adding a new page
**Use the template**: Copy `pages/0_empty.py` as a starting point. It includes:
- Complete page structure with all required imports
- Examples of using utilities from `utils.py`
- Common patterns (env vars, SQL queries, error handling)

**Manual steps**:
1. Create new file in `pages/` directory: `pages/N_page_name.py`
2. Add `st.set_page_config()` at top with page title and icon
3. Call `render_sidebar()` after set_page_config
4. Import utilities from `utils.py`: `from utils import get_env, sql_conn, workspace_client_obo, render_sidebar`
5. Add page content with `st.title()` and your components
6. Streamlit will automatically discover and add it to navigation
7. **Delete `pages/0_empty.py`** after creating your first actual page (it's just a template reference)

**Note**: The file number prefix determines display order (e.g., `0_`, `1_`, `2_`, `3_`)

### Adding a new resource dependency
1. Add resource in Databricks Apps UI with a key (e.g., `my-resource`)
2. Add to `app.yaml` env section:
   ```yaml
   - name: MY_RESOURCE_ID
     valueFrom: my-resource
   ```
3. Access in code: `resource_id = get_env("MY_RESOURCE_ID")` (import from `utils`)

### Modifying authentication
- **SQL queries**: Change `credentials_provider` in `sql_conn()` in `utils.py`
- **Genie/SDK calls**: Modify token passed to `WorkspaceClient()` in `workspace_client_obo()` in `utils.py`
- **User info**: Extract from `st.context.headers` (see `render_user_badge()` in `utils.py` for available headers)

### Working with Unity Catalog tables
**IMPORTANT**: Do not guess table schemas, column names, or filter values without inspecting the actual table first.

---

## Streamlit-Specific Patterns Used

- **`st.set_page_config()`**: Must be first Streamlit command in each file (`app.py` and each page file)
- **`st.logo()`**: Sidebar logo (called within `render_sidebar()` in `utils.py`)
- **`@st.cache_resource`**: For connection objects (`sql_conn()` in `utils.py`)
- **Multipage apps**: Automatic page discovery from `pages/` directory (Streamlit standard pattern)
- **`st.chat_message()` + `st.chat_input()`**: For building chat UIs (see cookbook examples)
- **`components.iframe()`**: For embedding external content with iframe (dashboards, etc.)
- **`st.session_state`**: Persistent state across reruns and pages

### Common Import Mistakes

**Using components.iframe()** requires proper import:
```python
# CORRECT
import streamlit.components.v1 as components
components.iframe(url, height=600)
```

---

## Error Handling Philosophy

**Never crash the app**. Always:
1. Check for missing env vars with `get_env()` from `utils.py` → shows error + stops gracefully
2. Wrap external calls in try/except → show `st.error()` with context
3. Check for missing auth headers → show clear instructions in error message

Example:
```python
from utils import get_env

try:
    resource_id = get_env("MY_RESOURCE_ID")
    # ... operation ...
except Exception as e:
    st.error(f"Operation failed. Context: {e}")
```

---

## Key Files

- **`app.py`**: Main entrypoint with page config and home page
- **`utils.py`**: Shared utilities and connection builders (see file for all available functions)
- **`pages/`**: Directory for page files (auto-discovered by Streamlit)
  - `0_empty.py` - Template for creating new pages (copy this to start)
  - Add your pages here as `N_page_name.py`
- **`app.yaml`**: Runtime config (command + env mapping)
- **`requirements.txt`**: Python dependencies
- **`README.md`**: Deployment instructions and troubleshooting
- **`CLAUDE.md`**: This file - guidance for development
- **`cookbook/`**: Git submodule with Databricks Apps examples (Streamlit, Dash, FastAPI, etc.)

---

## References

When modifying this app, consult:
- [Databricks Apps Auth](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth) - OBO patterns
- [Genie Conversation API](https://docs.databricks.com/aws/en/genie/conversation-api) - API structure
- [Databricks Apps Cookbook](https://apps-cookbook.dev/) - Code samples
- [Streamlit Multipage](https://docs.streamlit.io/develop/api-reference/navigation/st.page) - Navigation API

### Local Cookbook Submodule

The `cookbook/streamlit/` directory contains the [Databricks Apps Cookbook](https://github.com/databricks-solutions/databricks-apps-cookbook) as a git submodule for Streamlit based examples.

**Available Streamlit Examples (cookbook/streamlit/views/):**

**Tables**
- `oltp_database_connect.py` - Query an OLTP database instance table
- `tables_read.py` - Query a Unity Catalog Delta table
- `tables_edit.py` - Interactively edit a Delta table in the UI

**Volumes**
- `volumes_upload.py` - Upload a file into a Unity Catalog Volume
- `volumes_download.py` - Download a Volume file

**AI / ML**
- `ml_serving_invoke.py` - Invoke a model across classical ML and LLMs with UI inputs
- `ml_vector_search.py` - Use Mosaic AI to generate embeddings and perform vector search
- `mcp_connect.py` - Connect to a Model Context Protocol server
- `ml_serving_invoke_mllm.py` - Send text and images for visual-language LLM tasks

**Business Intelligence**
- `embed_dashboard.py` - Embed an AI/BI dashboard
- `genie_api.py` - Embed a Genie space with chat interface

**Workflows**
- `workflows_run.py` - Trigger a job with job parameters
- `workflows_get_results.py` - Retrieve results for a Workflow Job run

**Compute**
- `compute_connect.py` - Transform data at scale with UI inputs

**Unity Catalog**
- `unity_catalog_get.py` - List catalogs and schemas, get metadata

**Authentication**
- `users_get_current.py` - Get current App user information
- `users_obo.py` - Run commands on behalf of a user (similar to our OBO pattern)

**External Services**
- `external_connections.py` - Connect to a Unity Catalog-governed HTTP endpoint
- `secrets_retrieve.py` - Get a sensitive API key without hard-coding it

Update the cookbook: `git submodule update --remote cookbook`
