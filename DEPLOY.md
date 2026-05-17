# Deployment

Two ways to deploy this app. Pick one — both produce a Databricks App you can open in the browser.

| Path | When to use |
|---|---|
| **A. Databricks Asset Bundle (recommended)** | Repeatable deploys, source-controlled resource bindings + permissions, CI-friendly. |
| **B. Manual sync + apps deploy** | One-off testing, no bundle setup, you configure permissions in the Apps UI yourself. |

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
