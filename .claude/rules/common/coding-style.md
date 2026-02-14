# Coding Style

## File Organization

- Prefer small, focused modules over large multi-purpose files.
- Keep page-specific UI logic in `pages/` and shared logic in `utils.py` or feature helpers.
- Use clear names for Databricks resources and environment keys.

## Error Handling

- Fail with user-facing context in Streamlit (`st.error`, `st.warning`) instead of silent failures.
- Keep exceptions explicit around external calls (Databricks SDK, SQL, HTTP).

## Data and Config Boundaries

- Validate required environment variables through `get_env()`.
- Never hardcode deploy-time values that belong in `app.yaml`.

## Readability

- Prefer straightforward code over clever abstractions.
- Add short comments only where behavior is non-obvious.
