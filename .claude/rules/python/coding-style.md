---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Coding Style

This file extends `../common/coding-style.md` with Python-specific expectations.

- Follow PEP 8.
- Add type annotations for new or modified function signatures.
- Prefer context managers for files and connections.
- Keep Streamlit callbacks and page handlers concise; move heavy logic into helpers.
