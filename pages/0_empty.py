"""Empty Page Template - Use this as a starting point for new pages."""
import streamlit as st
from utils import render_sidebar

# Configure page (must be first Streamlit command)
st.set_page_config(
    page_title="Empty Page",
    page_icon="📄",
    layout="wide"
)

# Render sidebar with logo and user badge
render_sidebar()

# Page content starts here
st.title("0 — Empty Page Template")

st.markdown("""
This is a template page showing the basic structure.

### What to include in every page:

1. **Docstring** at the top explaining the page purpose
2. **Import statements** - import `render_sidebar` and any utilities you need
3. **`st.set_page_config()`** - Must be the first Streamlit command
4. **`render_sidebar()`** - Renders logo and user badge
5. **Page title** with `st.title()`
6. **Your page content** - Add your components here

### Available utilities from `utils.py`:

- `get_env(name)` - Get required environment variable
- `get_user_token()` - Get user's access token
- `sql_conn()` - Get SQL connection with user auth
- `workspace_client_obo()` - Get Workspace client with user token
- `render_sidebar()` - Render logo and user badge (already called above)

### Example: Reading an environment variable

```python
from utils import get_env

table_name = get_env("MY_TABLE_NAME")
st.write(f"Table: {table_name}")
```

### Example: Querying a table

```python
from utils import sql_conn

try:
    with sql_conn().cursor() as cur:
        cur.execute("SELECT * FROM my_table LIMIT 10")
        df = cur.fetchall_arrow().to_pandas()
    st.dataframe(df, use_container_width=True)
except Exception as e:
    st.error(f"Query failed: {e}")
```

---

**To create a new page:**
1. Copy this file to `pages/N_your_page_name.py` (where N is the order number)
2. Update the docstring, page config, and title
3. Add your page content
4. Streamlit will automatically discover and add it to navigation
""")

st.info("💡 Delete this page or rename it when you're done using it as a reference!")
