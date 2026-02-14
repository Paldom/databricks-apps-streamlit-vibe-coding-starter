---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Testing

This file extends `../common/testing.md` with Python specifics.

- Use `pytest` for Python tests.
- Organize tests under `tests/` when adding new test suites.
- Validate failure paths (missing env vars, auth issues, Databricks API errors).
