"""NYC Taxi Dashboard — embedded AI/BI dashboard.

Renders the AI/BI dashboard built over ``demo.nyctaxi.v_trips_genie`` inside
an iframe. The page itself does NOT query the warehouse — the dashboard's
own credentials (published with ``embed_credentials=true``) drive the
visuals, so any signed-in app user can see the data without needing UC
``SELECT`` on the underlying view.
"""
import streamlit as st
import streamlit.components.v1 as components

from utils import get_env, init_page

init_page(page_title="NYC Taxi Dashboard", page_icon=":material/dashboard:")

st.title("NYC Taxi Dashboard")
st.caption(
    "Interactive AI/BI dashboard backed by `demo.nyctaxi.v_trips_genie` — "
    "21,932 trips across Jan 1 – Feb 29, 2016."
)

dashboard_url = get_env("DASHBOARD_EMBED_URL")

# `streamlit.components.v1.iframe` is the supported way to embed iframes in a
# Streamlit app. `st.iframe` does NOT exist; using it raises AttributeError.
# `scrolling=True` lets users scroll inside the iframe when content overflows.
components.iframe(src=dashboard_url, height=1100, scrolling=True)
