# Testing Guidelines

- For bug fixes, add a regression test when practical.
- For new logic, prefer unit tests on helper functions before UI-heavy integration tests.
- Keep tests deterministic; mock external services and network dependencies.
- Run at least syntax validation (`python3 -m py_compile`) for edited Python files.
