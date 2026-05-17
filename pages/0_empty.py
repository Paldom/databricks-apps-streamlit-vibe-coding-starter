"""Empty Page Template - Use this as a starting point for new pages."""
import streamlit as st

from utils import init_page

# Bootstrap: page config + Databricks logo + user badge. Must be the first
# Streamlit command on the page.
init_page(page_title="Empty Page")

st.title("Empty Page Template")

st.markdown(
    """
This is a template page showing the basic structure.

### What to include in every page

1. **Docstring** at the top explaining the page purpose.
2. **Import** `init_page` from `utils` (plus any helpers you need).
3. **Call `init_page(page_title=...)`** as the very first Streamlit
   command — it runs `st.set_page_config()`, registers the Databricks
   logo, and renders the signed-in user badge in one place.
4. **Page title** with `st.title()` and your page content below.

### Available utilities from `utils.py`

- `get_env(name)` — required env var with friendly failure.
- `get_user_token()` — forwarded user access token (OBO).
- `sql_conn()` — DB-SQL connection scoped to the signed-in user.
- `workspace_client_app()` — SDK client using the app service principal
  (use for APIs that handle OBO internally, e.g. Genie).
- `workspace_client_obo()` — SDK client using the user's forwarded token.

### Example: reading an environment variable

```python
from utils import get_env

table_name = get_env("MY_TABLE_NAME")
st.write(f"Table: {table_name}")
```

### Example: querying a table

```python
from utils import sql_conn

try:
    with sql_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM my_table LIMIT 10")
        df = cur.fetchall_arrow().to_pandas()
    st.dataframe(df, use_container_width=True)
except Exception as e:
    st.error(f"Query failed: {e}")
```

---

**To create a new page:**

1. Copy this file to `pages/N_your_page_name.py` (where `N` is the order number).
2. Update the docstring, page title, and content.
3. Streamlit auto-discovers files under `pages/` and adds them to the sidebar.
"""
)

st.info("Delete this page or rename it when you're done using it as a reference.")
