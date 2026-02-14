---
description: "Create a new Streamlit page from the local template and wire baseline structure."
allowed-tools: ["Bash", "Read", "Write", "Edit"]
---

# /new-streamlit-page

Create a new page using `pages/0_empty.py` as the template.

## Inputs

- `$ARGUMENTS` should be: `<order> <slug>`
- Example: `2 catalog_explorer`

This creates:
- `pages/2_catalog_explorer.py`

## Steps

1. Validate the template exists (`pages/0_empty.py`).
2. Validate `order` is numeric and slug is snake_case.
3. Copy template to the new page path.
4. Update page title/icon/header placeholders in the new file.
5. Keep:
   - `st.set_page_config(...)` at top
   - `render_sidebar()` call
   - `get_env()` pattern for required env vars
6. Show the created file path and a short TODO list for feature-specific logic.

If the target file already exists, stop and ask for confirmation before overwrite.
