# Implementation Plan — GitHub Actions CI/CD

One-time setup for the minimalist CI/CD pipeline shipped under `.github/workflows/`: a `CI` workflow that runs on every PR with no Databricks calls, and a `Deploy` workflow that runs `bundle validate → deploy → run` against the `dev` target on every push to `main`.

> **Run order.** Complete `0_A_initial_setup.md` first — this plan assumes `databricks.yml`, the App, and the bundle's `dev` target already exist. It does not assume `0_B_design_system.md` is done; CI/CD is brand-agnostic.

> **Sources.** Databricks GitHub OIDC docs: https://docs.databricks.com/aws/en/dev-tools/auth/provider-github. The expanded design (preview environments, multi-workspace promotion, Lakebase branches) is documented in `.local/cicd/CICD-ARTICLE-v2.md`; this plan implements the **minimalist** slice of it.

> **DAB-relevant note.** The `Deploy` workflow runs `databricks bundle deploy -t dev`, which now creates substantially more than the App alone — schemas, the volume, the Lakebase stack, the dashboard, and every app resource binding. `scripts/bootstrap.py` (tables / views / PDF uploads / Agent Bricks artefacts) is **not** invoked from CI today — it's a one-off after-deploy step for fresh workspaces. If you want it CI-driven, add a third step to `deploy.yml` after the `bundle run` line: `uv run python scripts/bootstrap.py --warehouse-id $WAREHOUSE_ID --app-sp-client-id $APP_SP_CLIENT_ID --skip-uploads`. The `--skip-uploads` is optional but recommended in CI (uploads are slow + the volume content rarely changes between deploys).

---

## Pick an auth path before going further

This plan documents two ways for GitHub Actions to authenticate to Databricks. Pick one **first** — every step downstream is labelled **A** or **B**, and the steps that are not yours can be skipped.

| | **A. GitHub OIDC** *(recommended)* | **B. Client ID + secret** |
|---|---|---|
| What GitHub stores | Workspace host + SP client ID as Environment **secrets** (so they get masked in logs — see §4.3). | The same plus `DATABRICKS_CLIENT_SECRET`, all as Environment **secrets**. |
| Long-lived secret | **None.** Each run mints a short-lived OIDC token; Databricks exchanges it for a workspace token. | One OAuth M2M secret, valid until rotated. |
| Databricks-side setup | Create SP **+** create a federation policy binding the GitHub repo+environment to that SP. | Create SP **+** generate an OAuth M2M secret on the SP. |
| Workflow env vars | `DATABRICKS_AUTH_TYPE=github-oidc`, `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID` | `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET` |
| GitHub permissions | `id-token: write` required on the job. | Default permissions only. |
| Rotation | Update the federation policy, no GitHub change. | Rotate the OAuth secret + update the GitHub secret. |
| Forks / public repo | Safe — fork PRs cannot use the OIDC token of the upstream. | Risky — fork PRs would expose the secret if not guarded by an Environment. |
| Setup effort | ~10 min (extra federation policy step). | ~5 min. |

**Shipped default:** path **B** (client secret) — fewer Databricks-side prerequisites, works on Azure Databricks accounts where the account-level federation-policy CLI is not yet wired up. The shipped `.github/workflows/deploy.yml` is configured for path B.

**Recommendation (long-term):** path **A (OIDC)** for any repo that will live longer than a sprint — no secret to rotate, fork-PR safe. Switch to path A via the three-line patch in §5.3 once your account-level CLI auth is working.

---

## 1. Parameters to set

| Parameter | Where it lives | Path | Notes |
|---|---|---|---|
| Auth path | this plan + how you configure GitHub & Databricks | A or B | Record your choice up front. |
| Deploy service principal (SP) | Databricks account console → Service principals | A and B | Capture both **UUID** (used in federation-policy / secret-create CLI calls) and **Application ID** (used as `DATABRICKS_CLIENT_ID` in GitHub). |
| Workspace host | GitHub Environment **secret** `DATABRICKS_HOST` | A and B | Deploy target's workspace URL, with scheme. Stored as a secret on public repos so it doesn't appear in logs (§4.3). |
| OAuth M2M secret | GitHub Environment secret `DATABRICKS_CLIENT_SECRET` | **B only** | One-shot value returned by `databricks account service-principal-secrets create` — copy it once. |
| GitHub org / repo / environment | Federation policy `subject` | **A only** | Subject must be `repo:<org>/<repo>:environment:<env>` for the OIDC token to match. |
| OIDC audience | Federation policy `audiences` | **A only** | Defaults to `https://github.com/<github_org>` when no explicit audience is requested by the workflow. |

### 1.1 Fill-in worksheet

Current setup uses **path B**. Path-A rows are kept for the future-upgrade path documented in §5.3.

- **`auth_path`** = `B` (client secret) — shipped default
- **`deploy_sp_application_id`** (used as `DATABRICKS_CLIENT_ID`) = `e2a8c2dc-d605-48e9-9cba-2f8bb4d84691`
- **`deploy_sp_workspace_numeric_id`** (workspace-level SP numeric ID, for reference) = `147227875503770`
- **`workspace_host`** = `https://adb-1272983411735654.14.azuredatabricks.net`
- **`github_org`** = `Paldom`
- **`github_repo`** = `databricks-apps-streamlit-vibe-coding-starter`
- **`github_environment`** = `dev`
- **B in use — `DATABRICKS_CLIENT_SECRET`** = stored as a GitHub Environment secret; OAuth M2M value generated on the SP via `databricks service-principal-secrets create`. Rotate via the same command + update the GitHub secret.
- **A (future) — `deploy_sp_account_uuid`** (account-level SP UUID — needed by `service-principal-federation-policy create`) = `__________________` *(look up via `databricks account service-principals list` once account auth is configured)*
- **A (future) — `oidc_audience`** = `https://github.com/Paldom`
- **A (future) — Federation subject** (computed) = `repo:Paldom/databricks-apps-streamlit-vibe-coding-starter:environment:dev`

---

## 2. Overview

**What the two workflows do.**

| File | Trigger | What runs | Auth |
|---|---|---|---|
| `.github/workflows/ci.yml` | Pull request, push to `main` | `uv sync --frozen`, `uv run python -m py_compile …` | None — no Databricks calls. Runs on fork PRs without any extra config. |
| `.github/workflows/deploy.yml` | Push to `main`, `workflow_dispatch` | `databricks bundle validate → deploy → run` against the `dev` target | Path **B** (client secret) as shipped, or path **A** (OIDC) after a three-line patch — see §5.3. |

**Why route through a GitHub Environment in both paths.**

- **Path A** — GitHub's OIDC token includes a `sub` claim shaped by where the workflow runs. Without an `environment:` key the subject contains the branch (`repo:org/repo:ref:refs/heads/main`) — workable, but it changes between branches and triggers, so any federation policy match becomes brittle. Routing every deploy job through a named GitHub Environment forces `sub = repo:org/repo:environment:<env>`, a stable string that the policy can match exactly. The Databricks docs explicitly recommend this.
- **Path B** — the Environment is what scopes the `DATABRICKS_CLIENT_SECRET` secret to specific branches/refs and gates it behind reviewers. Without it the secret would be available on any push, including from fork PRs.

GitHub Environments also bring required-reviewer / wait-timer / branch-restriction gating, which is how you stage `staging` and `prod` later (§6).

**Scope of "minimalist".** One target (`dev`), one Environment, one SP, no preview branches, no per-PR clones. §6 sketches the steps to scale up to `staging` / `prod` when needed — the workflows above already accept that path with minor additions.

**End-to-end flow (push to main):**

```
git push origin main
        │
        ├──> CI workflow:
        │       └─ uv sync --frozen + py_compile          (always; ~30 s)
        │
        └──> Deploy workflow (environment: dev):
                ├─ checkout @ pushed SHA
                ├─ uv setup + Databricks CLI setup
                ├─ auth: OIDC token exchange (A)  OR  client-secret OAuth M2M (B)
                ├─ bundle validate -t dev
                ├─ bundle deploy  -t dev                  (uploads code, updates App)
                └─ bundle run streamlit-demo -t dev       (starts / restarts App)
```

---

## 3. Prerequisites (Databricks side)

§3.1 and §3.2 apply to **both paths**. §3.3 splits into **A** (federation policy) or **B** (OAuth secret). §3.4 is the Claude Code prompt that automates whichever you picked.

### 3.1 Create the deploy service principal *(A + B)*

Account-level SPs work cleanly for both paths. Create one named e.g. `gha-streamlit-demo-deploy-dev`:

```bash
databricks account service-principals create \
  --json '{"displayName":"gha-streamlit-demo-deploy-dev","active":true}'
```

Capture the response — note `id` (the UUID, used by federation-policy / secret-create CLI calls) and `applicationId` (used as `DATABRICKS_CLIENT_ID` in GitHub).

Add the SP to the target workspace:

```bash
databricks service-principals create \
  --application-id <deploy_sp_application_id> \
  --display-name "gha-streamlit-demo-deploy-dev" \
  --active
```

### 3.2 Grant the SP what it needs in the workspace *(A + B)*

The SP runs `bundle deploy` + `bundle run`, so it needs:

- **Workspace access** — workspace user role (default for added SPs).
- **App management** — either add the SP to `<user_group_manage>` (the group already granted `CAN_MANAGE` on the App in `databricks.yml`), or add an explicit permission line (see §5.4).
- **Resource grants required by your pages.** For the Sample Data page after `1_sample_data_page.md`: `CAN_USE` on the SQL warehouse and `SELECT` on `UNITY_CATALOG_TABLE`.

Simplest path: put the SP into `<user_group_manage>`; the bundle already grants that group `CAN_MANAGE`.

### 3.3.A *(path A only)* Create the GitHub-OIDC federation policy

This is the trust step — it tells Databricks to accept GitHub OIDC tokens with a specific subject as authentication for this SP.

```bash
databricks account service-principal-federation-policies create \
  --service-principal-id <deploy_sp_uuid> \
  --json '{
    "name": "github-streamlit-demo-dev",
    "description": "GitHub Actions, dev environment",
    "oidc_policy": {
      "issuer": "https://token.actions.githubusercontent.com",
      "audiences": ["https://github.com/<github_org>"],
      "subject": "repo:<github_org>/<github_repo>:environment:dev"
    }
  }'
```

Key fields:

- `issuer` — fixed; GitHub's OIDC issuer URL.
- `audiences` — defaults to `https://github.com/<your-org>` when no explicit audience is requested by the workflow. If you later add `aud:` to the `actions/checkout` token request, match it here.
- `subject` — must match the workflow's claim **exactly**. Routing through the `dev` GitHub Environment produces `repo:<org>/<repo>:environment:dev`. No wildcards — one policy per Environment (max 20 federation policies per SP, the practical cap on how many Environments share one SP).

### 3.3.B *(path B only)* Generate an OAuth M2M secret on the SP

```bash
databricks account service-principal-secrets create \
  --service-principal-id <deploy_sp_uuid>
```

The response contains a one-shot `secret` field. **Copy it immediately** — Databricks does not show it again. Paste it into the GitHub Environment secret in §4.2.B.

You may add a comment or a lifetime via the request body; defaults are fine for a starter.

### 3.4 Claude Code prompt — provision the SP and your chosen path

With the Databricks MCP server attached, paste this and let Claude do §3.1 / §3.2 plus the right branch of §3.3 idempotently. Fill in §1.1 first.

```text
Please provision the deploy service principal described in
docs/plans/0_C_github_actions.md.

Inputs:
- auth_path:                    <A or B>
- github_org:                   <github_org>
- github_repo:                  <github_repo>
- github_environment:           dev
- workspace_host:               <workspace_host>
- user_group_manage:            <user_group_manage from 0_A_initial_setup.md>

Do the following, idempotently (skip if it already exists), and report
each change you make:

1. Create an account-level service principal named
   gha-streamlit-demo-deploy-dev (if it does not exist).
2. Add the SP to the workspace at <workspace_host>.
3. Add the SP to the workspace group <user_group_manage> so it
   inherits CAN_MANAGE on the App declared in databricks.yml.

4. Branch on auth_path:
   - If A: create a service-principal federation policy on the SP with
     - issuer:    https://token.actions.githubusercontent.com
     - audiences: ["https://github.com/<github_org>"]
     - subject:   repo:<github_org>/<github_repo>:environment:dev
     and print success.
   - If B: generate an OAuth M2M secret on the SP and print the
     one-shot secret value. WARN me that this value is shown once
     and must be pasted into the GitHub Environment secret
     DATABRICKS_CLIENT_SECRET immediately.

5. Print the SP's applicationId — I need to paste it into the GitHub
   Environment variable DATABRICKS_CLIENT_ID.

Before mutating anything, print the plan of changes and wait for me to
confirm.
```

---

## 4. Prerequisites (GitHub side)

§4.1 applies to **both paths**. §4.2 splits into **A** (variables only) and **B** (variables + secret). §4.3 / §4.4 are common.

### 4.1 Create the `dev` GitHub Environment *(A + B)*

GitHub UI → **Settings → Environments → New environment → `dev`**.

Leave protection rules empty for `dev`. For `staging` / `prod` later, add required reviewers + branch/tag restrictions here.

### 4.2.A *(path A only)* Add Environment secrets

Inside the `dev` Environment, add two **secrets**:

- `DATABRICKS_HOST` = your workspace URL (with `https://`).
- `DATABRICKS_CLIENT_ID` = the SP's *Application ID* from §3.1.

Strictly speaking neither value is confidential, but on a **public repo** storing them as secrets (not variables) gives you GitHub's automatic log-masking — workspace URLs and client IDs reveal target infrastructure to anyone scrolling through action logs.

### 4.2.B *(path B only)* Add Environment secrets

The same two secrets as path A:

- `DATABRICKS_HOST` = your workspace URL.
- `DATABRICKS_CLIENT_ID` = the SP's *Application ID*.

…plus the OAuth M2M secret:

- `DATABRICKS_CLIENT_SECRET` = the value printed by §3.3.B.

All three live as **Environment** secrets (not repository secrets) so that fork PRs and `pull_request_target` workflows cannot read them.

### 4.3 Lock down the `dev` Environment *(A + B, essential on a public repo)*

In **Settings → Environments → `dev`**, configure three protection rules. None of them require a paid plan on public repos.

1. **Deployment branches and tags** → "Selected branches and tags" → add rule: `main`.
   Prevents `workflow_dispatch` from running the Deploy workflow against any other ref. Without this rule, anyone with write access could pick a feature branch in the dispatch UI and ship untested code.

2. **Required reviewers** → add yourself (or a small admins team).
   Every deployment pauses at the `deploy` job until you click **Approve** in the GitHub UI. One click; a stray push to `main` cannot auto-ship. For path A the OIDC token is minted *after* approval, so the federation policy match still works; for path B the secrets are released to the job at the same point.

3. **Wait timer** *(optional)* → e.g. 5 minutes.
   Adds an "oh no" window in which you can still cancel the run from the Actions UI before it executes. Independent of the human approval gate.

Combined effect: deployments only ever run from `main`, only with explicit human approval, and the secrets used during the run never appear in workflow logs.

### 4.4 OIDC enabled at org level *(A only)*

Defaults are correct on personal/org repos created after 2023. If you previously hardened the org with `oidc.token: disabled`, re-enable it (Settings → Actions → General → Workflow permissions). The deploy workflow file requests `permissions: id-token: write` at the job level.

For path B, leave this alone — the workflow does not request `id-token: write` after the §5.3 patch.

### 4.5 Branch protection *(A + B, recommended)*

Settings → Branches → `main` → require status check `CI / python` before merging. The CI workflow runs on every PR; this stops broken code from reaching `main`, which is the only ref the Deploy workflow listens to.

### 4.6 Editor / linter warnings before setup

The GitHub Actions language server reports pre-setup issues that look like errors but are not:

```
deploy.yml:
  ✘ Value 'dev' is not valid                            # Environment doesn't exist YET
  ⚠ Context access might be invalid: DATABRICKS_HOST    # Environment secret not defined YET
  ⚠ Context access might be invalid: DATABRICKS_CLIENT_ID
```

All three clear once the `dev` Environment + its secrets are created (§4.1 + §4.2). They do not prevent the workflow from running and they do not affect already-pushed branches.

---

## 5. Source code updates

### 5.1 `.github/workflows/ci.yml` (shipped, unchanged for both paths)

PR + main-branch sanity. No Databricks calls, no OIDC, runs on fork PRs.

```yaml
on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with: { enable-cache: true }
      - run: uv sync --frozen
      - run: uv run python -m py_compile app.py utils.py pages/0_empty.py
```

Extend with `ruff`, `pytest`, or `mypy` steps if/when those are added — same job, no extra plumbing needed.

### 5.2 `.github/workflows/deploy.yml` (shipped — path B, client secret)

```yaml
on:
  push: { branches: [main] }
  workflow_dispatch:
    inputs:
      ref: { description: "Git ref to deploy", required: true, default: main }

permissions:
  contents: read           # client-secret auth — no id-token: write needed

concurrency:
  group: deploy-dev
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: dev       # scopes the secret + gates with reviewer rule
    env:
      DATABRICKS_HOST: ${{ secrets.DATABRICKS_HOST }}
      DATABRICKS_CLIENT_ID: ${{ secrets.DATABRICKS_CLIENT_ID }}
      DATABRICKS_CLIENT_SECRET: ${{ secrets.DATABRICKS_CLIENT_SECRET }}
    steps:
      - uses: actions/checkout@v4
        with: { ref: ${{ inputs.ref || github.ref }} }
      - uses: astral-sh/setup-uv@v3
        with: { enable-cache: true }
      - uses: databricks/setup-cli@main
      - run: databricks bundle validate -t dev
      - run: databricks bundle deploy  -t dev
      - run: databricks bundle run streamlit-demo -t dev
```

Key points:

- **OAuth M2M auto-detected.** The Databricks CLI picks this auth mode whenever `DATABRICKS_CLIENT_ID` + `DATABRICKS_CLIENT_SECRET` are both set — no `DATABRICKS_AUTH_TYPE` needed.
- **`permissions: contents: read` only.** Client-secret auth does not request a GitHub OIDC token, so `id-token: write` is omitted. Removing it shrinks the job's blast radius.
- **All three workspace identifiers come from `secrets.*`, not `vars.*`.** On a public repo this is what gets `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, and `DATABRICKS_CLIENT_SECRET` masked in workflow logs (see §4.2 / §4.3).
- **`bundle run` is intentional.** `bundle deploy` uploads code but does **not** restart the App process; the explicit `bundle run streamlit-demo -t dev` is what makes the new code go live.
- **`environment: dev`** does two jobs at once: scopes the three secrets to this environment (fork PRs cannot read them) and gates the run behind the required-reviewer rule from §4.3.
- **`cancel-in-progress: false`** — never cancel an in-flight deploy. The concurrency group serialises pushes.

### 5.3 *(path A only)* Switch `deploy.yml` to GitHub OIDC

When the account-level federation policy is in place (§3.3.A), apply this patch to drop the long-lived secret. Three lines change: add the `id-token: write` permission, add `DATABRICKS_AUTH_TYPE=github-oidc`, and remove the `DATABRICKS_CLIENT_SECRET` env entry.

```diff
 permissions:
   contents: read
+  id-token: write          # required for GitHub OIDC

 jobs:
   deploy:
     runs-on: ubuntu-latest
     environment: dev
     env:
+      DATABRICKS_AUTH_TYPE: github-oidc
       DATABRICKS_HOST: ${{ secrets.DATABRICKS_HOST }}
       DATABRICKS_CLIENT_ID: ${{ secrets.DATABRICKS_CLIENT_ID }}
-      DATABRICKS_CLIENT_SECRET: ${{ secrets.DATABRICKS_CLIENT_SECRET }}
```

Result, in full:

```yaml
permissions:
  contents: read
  id-token: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: dev
    env:
      DATABRICKS_AUTH_TYPE: github-oidc
      DATABRICKS_HOST: ${{ secrets.DATABRICKS_HOST }}
      DATABRICKS_CLIENT_ID: ${{ secrets.DATABRICKS_CLIENT_ID }}
    steps: ...    # unchanged
```

After switching, **delete the `DATABRICKS_CLIENT_SECRET` Environment secret** in GitHub and **revoke the SP secret** on the Databricks side (`databricks account service-principal-secrets delete --service-principal-id <uuid> --secret-id <id>`). Leaving them around defeats the security benefit of OIDC.

### 5.4 Optional: declare the SP in `databricks.yml` *(A + B)*

If you would rather not put the SP into `<user_group_manage>`, add it directly to the bundle's permissions block. Open `databricks.yml` and add a third entry under `permissions`:

```yaml
resources:
  apps:
    streamlit-demo:
      permissions:
        - level: CAN_MANAGE
          group_name: ${var.user_group_manage}
        - level: CAN_USE
          group_name: ${var.user_group_app}
        - level: CAN_MANAGE
          service_principal_name: ${var.deploy_sp_app_id}   # NEW
```

…and declare the new variable + default:

```yaml
variables:
  deploy_sp_app_id:
    description: "Application ID of the GitHub Actions deploy service principal."

targets:
  dev:
    variables:
      deploy_sp_app_id: "<deploy_sp_application_id>"
```

This is more auditable (the SP's authority is named in source control) but slightly more verbose. Pick one approach; don't do both.

---

## 6. Scaling up later

The minimalist setup is one Environment + one SP + one target. To stretch toward the full design in `.local/cicd/CICD-ARTICLE-v2.md`:

1. **Add a `staging` Environment** in GitHub → matching SP (and federation policy if on path A, or secret if on path B) in Databricks → matching `staging` DAB target.
2. **Add a `prod` Environment** with **required reviewers** + restrict deployments to tags (`v*`). For path A, the federation policy subject is `repo:<org>/<repo>:environment:prod`.
3. **Generalise the workflow**: replace the hard-coded `-t dev` with `inputs.target`, and key `environment:` off `inputs.target` so one workflow promotes through all three.
4. **PR previews**: a third workflow on `pull_request` events that reuses the `dev` target with `--var=<preview overrides>` for the App name and (if you adopt Lakebase) a per-PR branch.
5. **Lakebase / preview teardown**: a `delete` + hourly-cron workflow that runs `databricks bundle destroy --var=...` for stale slugs.

Every step above slots in without rewriting the auth pieces — the GitHub-Environment-as-gate pattern in this plan is the foundation regardless of whether you stay on A or B.

---

## Verification

1. **Local schema check** before pushing:
   ```bash
   uv run --with pyyaml python -c "import yaml,pathlib; [yaml.safe_load(pathlib.Path(p).read_text()) for p in ['.github/workflows/ci.yml','.github/workflows/deploy.yml']]; print('OK')"
   ```

2. **CI smoke** — open a throwaway PR that touches `app.py`. The `CI / python` job must finish green in under a minute. No Databricks calls; no OIDC or secret required.

3. **Deploy smoke** — merge a no-op change to `main`, or **Run workflow** on the Deploy workflow with `ref=main`. Watch:
   - The workflow pauses at the `deploy` job with a **Review deployments** banner (because of §4.3 required reviewer). Click **Approve and deploy**.
   - The `dev` Environment shows the run in the deployment history.
   - `databricks bundle deploy` finishes without auth errors.
   - `databricks bundle run streamlit-demo -t dev` returns a URL; opening it shows the new commit live.
   - **Public-repo hardening check** (both paths): the workspace URL is rendered as `***` in any log line that mentions it. Same for the client ID and (path B) the client secret. If you see the raw URL or client ID, you wired them as variables instead of secrets — go back to §4.2.
   - **Path B (shipped):** workflow log does **not** print `DATABRICKS_CLIENT_SECRET`; the masked-env section shows `DATABRICKS_CLIENT_*` entries; the CLI auto-detects OAuth M2M (no explicit `DATABRICKS_AUTH_TYPE` line in logs).
   - **Path A:** workflow log mentions an OIDC token exchange ("Reading the OIDC token from the runtime" or similar).

4. **Negative test — path A only — wrong subject.** Temporarily edit the federation policy `subject` to `…:environment:foo`. The next deploy must fail at the OIDC exchange with a clear "no matching federation policy" error. Restore the subject. This confirms the policy is the gate, not bypassed by some hidden credential.

5. **Negative test — path B only — secret revoked.** Revoke the OAuth M2M secret on the SP. The next deploy must fail with a 401 from the workspace. Generate a fresh secret, update the GitHub Environment secret, redeploy.

6. **Negative test — push to feature branch.** A push to `feature/x` must trigger only the `CI` workflow, never `Deploy`. This is enforced by `on.push.branches: [main]` in `deploy.yml`.

7. **Negative test — `workflow_dispatch` from a feature branch.** Open the Deploy workflow in the Actions UI, click **Run workflow**, pick branch `feature/x`. GitHub must refuse with "*Branch is not allowed to deploy to dev based on environment protection rules*" — proves §4.3 step 1 (deployment branches restricted to `main`) is in effect.

---

## What to avoid

- **(A) Storing `DATABRICKS_CLIENT_SECRET` "just in case".** Once OIDC works, the secret path is dead weight and a foot-gun. Remove the GitHub secret and revoke the SP secret on the Databricks side.
- **(A) Omitting `environment:` on the deploy job.** Without it, the OIDC `sub` claim is branch-shaped and the federation-policy match is brittle.
- **(B) Storing any of the three values as a *repository* secret instead of an *Environment* secret.** Repository secrets are exposed to fork PRs and to any workflow with `pull_request_target`. Always scope to the Environment.
- **(B) Forgetting that the secret is long-lived.** Set a rotation reminder. If the SP secret leaks, revoke it via `databricks account service-principal-secrets delete --service-principal-id <uuid> --secret-id <id>` and generate a new one — no code change needed.
- **(public repo) Storing `DATABRICKS_HOST` or `DATABRICKS_CLIENT_ID` as Environment *variables*.** They are not strictly confidential, but a public repo means workflow logs are world-readable. Variables print in plain text; secrets get auto-masked. Cost of using secrets is zero — just do it.
- **(public repo) Skipping the deployment-branch restriction in §4.3.** Without it, anyone with write access could pick a feature branch in `workflow_dispatch` and deploy untested code. The restriction is one rule in the Environment UI and pays for itself the first time someone tries.
- **(public repo) Skipping the required-reviewer rule in §4.3.** A force-push to `main`, a misconfigured GitHub App, or a stale-but-merged stale PR with bad code can all kick off a deploy. The reviewer rule turns those from "shipping" into "pending approval — please review".
- **(A + B) Granting the deploy SP account-admin.** The minimum is workspace-user + per-resource grants (App `CAN_MANAGE`, warehouse `CAN_USE`, table `SELECT`). The most common audit finding is dev groups silently inheriting on prod.
- **(A + B) Re-deploying without `bundle run`** and wondering why the new code didn't appear. `deploy` syncs files; only `run` restarts the App.
- **(A) Wildcards in the federation policy subject.** Not supported. Use one policy per Environment.
