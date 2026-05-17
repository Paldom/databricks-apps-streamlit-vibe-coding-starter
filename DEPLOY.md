# Deployment

Three ways to run this app. A and B produce a deployed Databricks App you open in the browser; C runs the app on your laptop with the same wiring Databricks Apps would inject in production.

| Path | When to use |
|---|---|
| **A. Databricks Asset Bundle (recommended)** | Repeatable deploys, source-controlled resource bindings + permissions, CI-friendly. |
| **B. Manual sync + apps deploy** | One-off testing, no bundle setup, you configure permissions in the Apps UI yourself. |
| **C. Local run via `databricks apps run-local`** | High-fidelity local development that mirrors the Apps runtime (resolves `valueFrom` resources, sets the same env vars, uses the `command` from `app.yaml`) without deploying. |

---

## A. Databricks Asset Bundle (recommended)

The repo ships with `databricks.yml` at the root. The shipped bundle is intentionally page-less: it declares the App and its permissions but no resource bindings. Per-page plans under `docs/plans/` add variables, resource bindings, and target values as you implement each page.

### 1. Prerequisites
- Databricks CLI **v0.218+** (`databricks --version`).
- Two user groups (or one reused for both): one for `CAN_MANAGE`, one for `CAN_USE` on the app.
- Per-page resources (SQL Warehouse, Genie Space, etc.) are added when you implement the page — see the corresponding plan under `docs/plans/`.

### 2. Fill in the dev target

Open `databricks.yml` and replace the `<...>` placeholders in `targets.dev.variables`:

```yaml
targets:
  dev:
    variables:
      user_group_manage: "<your-admin-group>"
      user_group_app:    "<your-users-group>"
```

### 3. Authenticate
```bash
databricks auth login --host https://<workspace-host>
```

### 4. Validate, deploy, run
```bash
databricks bundle validate -t dev
databricks bundle deploy  -t dev
databricks bundle run streamlit-demo -t dev
```

`bundle run` prints the live app URL.

### What `deploy` does
- Syncs the repo (excluding `docs/`, `.claude/`, `.github/`, `*.md`, caches, etc. — see `sync.exclude` in `databricks.yml`) to `/Workspace/Users/<you>/.bundle/streamlit-demo/dev/files`.
- Creates or updates the App `streamlit-demo` with that folder as `source_code_path`.
- Sets `CAN_MANAGE` / `CAN_USE` permissions on the app.
- Applies any per-page resource bindings (SQL warehouses, Genie spaces, …) declared under `resources.apps.streamlit-demo.resources`. The shipped bundle has none; per-page plans append them.

> User-authorization scopes (e.g. `sql`, `dashboards.genie`) are toggled in the Apps UI today, not by the bundle. Each per-page plan lists the scope its page needs.

### Common follow-up commands
```bash
databricks bundle deploy -t dev          # redeploy after code changes
databricks bundle destroy -t dev         # tear the App down
databricks bundle summary -t dev         # show resolved resource IDs + workspace paths
```

---

## B. Manual sync + apps deploy (alternative)

Use this if you do not want to maintain `databricks.yml`. You will configure permissions, per-page resource bindings, and user-authorization scopes by hand in the Apps UI.

```bash
# Live-sync the working directory to a workspace folder
databricks sync --watch . /Workspace/Shared/streamlit-demo

# In another terminal, push the app from that folder
databricks apps deploy streamlit-demo --source-code-path /Workspace/Shared/streamlit-demo
```

Then in the Apps UI:
1. Grant `CAN_MANAGE` / `CAN_USE` on the app to the appropriate user groups.
2. For each page you implement, add the resources and user-authorization scopes that the page's plan under `docs/plans/` calls for (e.g. a SQL Warehouse resource keyed `sql-warehouse` plus the `sql` scope for the Sample Data page).

---

## C. Local run via `databricks apps run-local` (development)

Iterate locally with the same env-var / resource wiring Databricks Apps will inject in production. Nothing is deployed — the app runs on your laptop, but `valueFrom` references are resolved against the workspace just like a real deploy.

### 1. Prerequisites
- Path A prerequisites (Databricks CLI v0.218+, `uv`, an authenticated CLI profile against the workspace).
- The Databricks App must already exist in the workspace. Run an initial deploy via path A or B so the App's resource bindings exist for `run-local` to read.

### 2. Prepare the environment and start the app
```bash
databricks apps run-local \
  --prepare-environment \
  --entry-point app.yaml
```

- `--prepare-environment` runs `uv sync` so the local `.venv` matches `uv.lock`. It requires `uv` on `PATH`.
- `--entry-point app.yaml` launches the `command` declared in `app.yaml` (e.g. `streamlit run app.py`).
- The CLI prints the local URL (default `http://localhost:8000`); open it in a browser. Databricks injects the `X-Forwarded-Access-Token` header so the same OBO-aware helpers in `utils.py` work without a code path for local-only auth.

### 3. Override env vars
The CLI inherits env-var bindings from the deployed App (`valueFrom` resolves against the workspace). Override or extend with one or more `--env` flags:

```bash
databricks apps run-local \
  --prepare-environment \
  --entry-point app.yaml \
  --env UNITY_CATALOG_TABLE=samples.nyctaxi.trips \
  --env SQL_WAREHOUSE_ID=<warehouse-id>
```

This is useful when iterating on a new page that has env vars Databricks does not know about yet — set them locally before you wire them into `app.yaml` / `databricks.yml`.

### 4. Debug
Attach a Python debugger by adding `--debug`:

```bash
databricks apps run-local \
  --prepare-environment \
  --entry-point app.yaml \
  --debug
```

The CLI prints the debugger connection details so your editor can attach.

### Notes
- The app's `source_code_path` is your current working directory; edits hot-reload via Streamlit, no redeploy needed.
- Without `--prepare-environment`, `run-local` skips `uv sync` and assumes the local `.venv` is already populated. Use this once you have a stable lockfile and want a faster restart.
- For a *no-Databricks-CLI* loop (just Streamlit, no resource resolution), use `uv run streamlit run app.py` instead — see [README § Local Development](README.md#local-development).
