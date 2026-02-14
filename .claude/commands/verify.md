---
description: "Run repo verification checks for this Streamlit/Python starter."
allowed-tools: ["Bash", "Read", "Grep"]
---

# /verify

Run verification for the current branch.

## Modes

- `quick`: syntax + optional lint on changed Python files
- `full` (default): syntax + optional lint + optional tests + git status

## Steps

1. Resolve target files:
   - Prefer changed Python files from `git diff --name-only -- '*.py'`
   - Fallback to `app.py`, `utils.py`, and `pages/*.py`
2. Run syntax validation:
   - `python3 -m py_compile <target-files>`
3. If `ruff` is available, run:
   - `ruff check <target-files>`
4. If mode is `full` and pytest inputs exist (`tests/` or `pytest.ini`), run:
   - `pytest -q`
5. Show summary + `git status --short`

## Report Format

```text
VERIFICATION: PASS|FAIL

Syntax: OK|FAIL
Ruff:   OK|SKIPPED|FAIL
Tests:  OK|SKIPPED|FAIL
Git:    <short status>
```

If any check fails, include exact command output and the first actionable fix.
