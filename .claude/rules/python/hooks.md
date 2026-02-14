---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Hook Expectations

This file extends `../common/hooks.md` for Python hook behavior.

Configured hooks should:
- warn on `print()` usage in app code,
- run quick Python syntax checks on edited files,
- avoid blocking workflows unless there is a hard failure.
