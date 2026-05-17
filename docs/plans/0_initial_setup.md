# Implementation Plan — Initial App Setup

One-time setup for this Streamlit-on-Databricks-Apps starter in a new workspace. Complete this plan before any per-page plan (e.g., `1_sample_data_page.md`). Per-page plans assume the scaffolding here is already in place and reuse the values from §1.1.

---

## 1. Parameters to set

The starter itself is small. Fill in the worksheet below — per-page plans cross-reference these names.

| Parameter | Where it lives | Notes |
|---|---|---|
| `app_name` | `databricks.yml` (bundle name + apps key + app `name`) | Must be globally unique inside the workspace. |
| `bundle_name` | `databricks.yml` `bundle.name` | Usually equal to `app_name`. |
| `workspace_host` | CLI profile + DAB | Used by `databricks auth login`. No scheme. |
| `user_group_manage` | `databricks.yml` permissions | Receives `CAN_MANAGE` on the app. |
| `user_group_app` | `databricks.yml` permissions | Receives `CAN_USE` on the app and on per-page resources. |
| `deploy_target` | DAB CLI `-t` flag | `dev` by default. |

### 1.1 Fill-in worksheet

- **`app_name`** = `__________________`
- **`bundle_name`** = `__________________`
- **`workspace_host`** (e.g. `adb-12345.6.azuredatabricks.net`) = `__________________`
- **`user_group_manage`** = `__________________`
- **`user_group_app`** = `__________________`
- **`deploy_target`** = `dev`

---

## 2. Overview

**What you get.** A Streamlit application configured for Databricks Apps with on-behalf-of (OBO) authentication. The app reads the signed-in user's identity from a forwarded access-token header and passes it to downstream Databricks calls, so Unity Catalog row/column policies are enforced for that user.

**Files at the repo root after this plan:**

| File | Purpose |
|---|---|
| `app.py` | Streamlit entrypoint: page config, sidebar, home content. |
| `utils.py` | Shared helpers — `get_env`, `get_user_token`, `sql_conn`, `workspace_client_app`, `workspace_client_obo`, `render_sidebar`. |
| `app.yaml` | Apps runtime config: launch command + env-var bindings (empty baseline; per-page plans append). |
| `requirements.txt` | Python dependencies. |
| `databricks.yml` | DAB bundle definition (created in section 4). |
| `assets/logo.svg` | Sidebar logo rendered by `render_sidebar()`. |
| `pages/` | Empty directory; Streamlit auto-discovers any `*.py` file inside it as a sidebar page. |

**Authentication model.** When *User authorization* is enabled, Databricks Apps injects two relevant headers on every request:

- `X-Forwarded-Access-Token` — the user's access token. `utils.get_user_token()` reads it and feeds it to OBO calls.
- `X-Forwarded-Email` — used by `render_sidebar()` for the user badge.

Two SDK clients are exposed:

- `workspace_client_app()` — uses the App's own service principal. Use for APIs that handle OBO internally (e.g., Genie).
- `workspace_client_obo()` — uses the forwarded user token. Use for SDK calls that must run as the signed-in user.

**How feature pages plug in.** Each page is a file dropped under `pages/`. Page-specific resource bindings (SQL warehouse, Genie space, model endpoint, etc.) are added on top of the scaffolding here via per-page plans. Nothing in this initial-setup plan binds you to a particular data source.

---

## 3. Prerequisites

### 3.1 Local tooling — install ai-dev-kit first

The repo expects the Databricks MCP server (and the Claude Code update-check hook) provided by **ai-dev-kit**. The MCP / IDE config files in this repo are checked in as `*.template`s with `<YOUR_USERNAME>` placeholders; you copy them to live names after installing the kit. Until this step is done, the Databricks MCP tools and the SessionStart hook will not work.

1. **Install ai-dev-kit** per your organisation's instructions. The default layout is:
   ```
   ~/.ai-dev-kit/.venv/bin/python                        # interpreter
   ~/.ai-dev-kit/repo/databricks-mcp-server/run_server.py
   ~/.ai-dev-kit/repo/.claude-plugin/check_update.sh
   ```
2. **Copy template configs** into the live filenames this repo expects, and replace `<YOUR_USERNAME>` with your OS username (the directory under `/Users/`):
   ```bash
   cp .mcp.json.template            .mcp.json
   cp .cursor/mcp.json.template     .cursor/mcp.json
   cp .vscode/mcp.json.template     .vscode/mcp.json
   cp .codex/config.toml.template   .codex/config.toml
   cp .claude/settings.json.template .claude/settings.json
   # Then edit each file and replace <YOUR_USERNAME>.
   # On macOS this one-liner does it in place:
   sed -i '' "s/<YOUR_USERNAME>/$(id -un)/g" \
     .mcp.json .cursor/mcp.json .vscode/mcp.json .codex/config.toml .claude/settings.json
   ```
   The live files are gitignored, so they will not be committed.
3. **Databricks CLI v0.218+** (`databricks --version`).

### 3.2 Workspace
- A Databricks workspace where Databricks Apps is available.
- Permission to create apps (workspace admin or app-creation entitlement).

### 3.3 Authenticate the CLI
```bash
databricks auth login --host https://<workspace_host>
```
This picks up an OAuth user token used by `databricks bundle ...` commands and by the MCP tools.

### 3.4 User groups
Create or identify two groups (or reuse one for both):

- `<user_group_manage>` — receives `CAN_MANAGE` on the app.
- `<user_group_app>` — receives `CAN_USE` on the app and on any per-page resources added later.

### 3.5 Claude Code prompt — provision the app shell

If Claude Code is wired up to the Databricks MCP server, paste the prompt below to provision an empty App and its baseline permissions. Per-page plans handle resource bindings and scope additions; do not add them here.

```text
Please stand up the empty Databricks App skeleton described in
docs/plans/0_initial_setup.md.

Inputs from my worksheet (section 1.1):
- app_name:          <app_name>
- workspace_host:    <workspace_host>
- user_group_manage: <user_group_manage>
- user_group_app:    <user_group_app>

Do the following, idempotently (skip if already configured) and report
each change you make:

1. Confirm the Databricks App <app_name> exists. If not, create it with
   no app resources, no env vars beyond the defaults, and no
   user-authorization scopes enabled.
2. Set the app's source_code_path to the current workspace folder.
3. Grant CAN_MANAGE on the app to <user_group_manage>.
4. Grant CAN_USE on the app to <user_group_app>.
5. Do NOT add SQL warehouses, Genie spaces, model endpoints, or other
   resources here — per-feature plans will add them.
6. Do NOT enable any user-authorization scopes yet — per-feature plans
   add the scopes they need.

Before mutating anything, print the plan of changes and wait for me to
confirm. Do not change permissions on objects not listed above.
```

The "wait for confirmation" line is deliberate; remove it only when running fully autonomously after the prompt has been reviewed.

---

## 4. DAB configuration

The repo ships with `databricks.yml` at the root. **You do not create it from scratch** — edit the placeholders in the `dev` target. The shipped bundle already contains the resource bindings needed by the pages that ship with this repo (see per-page plans for which page adds what); strip them if you remove the corresponding pages.

### 4.1 Edit `databricks.yml`

Update `targets.dev.variables` with the values from §1.1 and your SQL warehouse ID:

```yaml
targets:
  dev:
    variables:
      user_group_manage: "<user_group_manage>"
      user_group_app:    "<user_group_app>"
      sql_warehouse_id:  "<your-sql-warehouse-id>"
```

If you change `app_name` from the shipped default `streamlit-demo`, do a search-and-replace across `databricks.yml` — `bundle.name`, the key under `resources.apps`, and the `name:` field of the app resource must all match.

### 4.2 Minimum shape (reference)

For a from-scratch fork that drops every shipped page, the minimum bundle shape is below. Per-page plans extend this by adding entries to `variables`, `resources.apps.<app_name>.resources`, and `targets.dev.variables`.

```yaml
bundle:
  name: <bundle_name>

variables:
  user_group_manage:
    description: "User group with CAN_MANAGE on the app."
  user_group_app:
    description: "User group with CAN_USE on the app."

resources:
  apps:
    <app_name>:
      name: <app_name>
      source_code_path: ./
      permissions:
        - level: CAN_MANAGE
          group_name: ${var.user_group_manage}
        - level: CAN_USE
          group_name: ${var.user_group_app}
      resources: []   # per-page plans append entries here

sync:
  exclude:
    - .github/**
    - .claude/**
    - .local/**
    - .databricks/**
    - "**/__pycache__/**"
    - docs/**
    - cookbook/**
    - "*.md"
    - .DS_Store
    - .gitignore
    - .gitmodules

targets:
  dev:
    mode: development
    default: true
    variables:
      user_group_manage: "<user_group_manage>"
      user_group_app: "<user_group_app>"
```

### 4.3 Deploy
```bash
databricks bundle validate -t dev
databricks bundle deploy  -t dev
databricks bundle run <app_name> -t dev
```

### 4.4 Manual deploy alternative
If you do not want to maintain the bundle, see `DEPLOY.md` Path B — `databricks sync` + `databricks apps deploy`. With that flow you configure permissions and per-page resource bindings manually in the Apps UI.

---

## 5. Source code baseline

These root-level files must exist before any per-page plan can be applied.

### 5.1 `requirements.txt`
```text
streamlit
pandas
databricks-sql-connector
databricks-sdk
```

### 5.2 `utils.py`
```python
"""Shared utilities for Databricks Streamlit App."""
import hashlib
import os

import streamlit as st
from databricks import sql
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config


def get_env(name: str) -> str:
    """Read a required env var; on miss, render an error and stop."""
    val = os.getenv(name)
    if not val:
        st.error(f"Missing environment variable: {name}")
        st.stop()
    return val


def get_user_token() -> str:
    """Forwarded user access token; requires user authorization on the app."""
    token = (st.context.headers or {}).get("X-Forwarded-Access-Token")
    if not token:
        st.error(
            "User token not available. Ensure this app is opened as a "
            "Databricks App and User authorization is enabled with the "
            "scopes needed by the page (e.g. 'sql', 'dashboards.genie')."
        )
        st.stop()
    return token


def render_sidebar() -> None:
    """Render the logo + signed-in user badge."""
    st.logo("assets/logo.svg")
    headers = st.context.headers or {}
    email = headers.get("X-Forwarded-Email")
    avatar = None
    if email:
        md5 = hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest()
        avatar = f"https://www.gravatar.com/avatar/{md5}?s=64&d=identicon"
    with st.sidebar:
        st.markdown("#### Signed in")
        c1, c2 = st.columns([1, 3])
        with c1:
            if avatar:
                st.image(avatar, width=64)
        with c2:
            if email:
                st.caption(email)


def sql_conn():
    """Open a fresh DB-SQL connection per call, scoped to the signed-in user.

    Not cached: st.cache_resource is process-global and would leak one
    user's token to other sessions.
    """
    cfg = Config()
    warehouse_id = get_env("SQL_WAREHOUSE_ID")
    return sql.connect(
        server_hostname=cfg.host,
        http_path=f"/sql/1.0/warehouses/{warehouse_id}",
        access_token=get_user_token(),
    )


def workspace_client_app() -> WorkspaceClient:
    """App service principal; use for APIs that handle OBO internally (Genie)."""
    return WorkspaceClient()


def workspace_client_obo() -> WorkspaceClient:
    """User-scoped client; use for SDK calls that must run as the user."""
    return WorkspaceClient(token=get_user_token(), auth_type="pat")
```

### 5.3 `app.py`
```python
"""Databricks Streamlit App - Main Entrypoint."""
import streamlit as st

from utils import render_sidebar

st.set_page_config(
    page_title="Databricks Streamlit Starter",
    page_icon=":material/hub:",
    layout="wide",
)
render_sidebar()

st.title("Databricks Analytics")
st.markdown(
    "Welcome to the Databricks Streamlit starter. Feature pages added "
    "under `pages/` show up in the sidebar automatically."
)
```

### 5.4 `app.yaml`
Baseline only — no env vars yet. Per-page plans append entries to `env:`.
```yaml
command: ["streamlit", "run", "app.py"]

env: []
```

### 5.5 `assets/logo.svg`
Any SVG used as the sidebar logo. A placeholder is fine for the first deploy; replace with your branding later.

### 5.6 `pages/` directory
Create an empty directory at the repo root. Streamlit auto-discovers `*.py` files inside it as sidebar pages. Per-page plans drop files here.

---

## Verification

1. **Static check** from the repo root:
   ```bash
   python3 -m py_compile app.py utils.py
   ```
2. **Bundle validate**:
   ```bash
   databricks bundle validate -t dev
   ```
3. **Deploy and run**:
   ```bash
   databricks bundle deploy -t dev
   databricks bundle run <app_name> -t dev
   ```
4. **Smoke test in browser**
   - Open the app URL printed by `databricks bundle run`.
   - The home page renders, the sidebar shows the logo and signed-in email, no pages exist beyond the home view, the app log shows no errors.
5. **Auth sanity** — the home page must work even with no user-authorization scopes enabled. Forwarded headers are still injected; OBO calls are deferred until a feature page is added.
