---
description: "Review changed Python files for correctness, security, and Streamlit/Databricks patterns."
allowed-tools: ["Bash", "Read", "Grep", "Glob"]
---

# /python-review

Review current Python changes with focus on high-risk issues.

## Scope

1. Collect changed Python files with:
   - `git diff --name-only -- '*.py'`
2. If no Python files changed, report and stop.

## Review Checklist

### Correctness

- Broken imports or missing symbols
- Obvious runtime exceptions
- Incorrect Streamlit API usage (`set_page_config` placement, repeated side effects)

### Databricks Patterns

- Resource IDs or workspace values hardcoded instead of env-driven
- Wrong client choice (`workspace_client()` vs `workspace_client_obo()`)
- OBO header/token misuse

### Security

- Secret leakage in code
- Unsafe SQL construction
- Sensitive error messages shown directly to users

### Maintainability

- Missing type hints on changed public functions
- Duplicate logic that should live in `utils.py`
- Unclear naming or oversized functions

## Optional Tooling

If available, run:
- `ruff check <changed-python-files>`
- `python3 -m py_compile <changed-python-files>`

## Output

Provide findings sorted by severity with file and line references.
If no findings: explicitly state that and list residual risks (for example: tests not present or not run).
