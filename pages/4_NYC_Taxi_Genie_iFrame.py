"""NYC Taxi Genie — embedded AI/BI Genie Space.

Renders the published Genie Space built over ``demo.nyctaxi.v_trips_genie``
inside an iframe. Users can ask natural-language questions directly in the
embedded chat UI; the Streamlit page itself does NOT call the Genie
Conversation API — Genie runs against the workspace, so any signed-in app
user inherits their own Genie / Unity Catalog permissions on the source view.
"""
import streamlit as st
import streamlit.components.v1 as components

from utils import get_env, init_page

init_page(page_title="NYC Taxi Genie", page_icon=":material/smart_toy:")

st.title("NYC Taxi Genie")
st.caption(
    "Ask natural-language questions about `demo.nyctaxi.v_trips_genie` — "
    "trip counts, fares, distances, durations, pickup / dropoff ZIPs, "
    "routes, and pickup-time trends."
)

genie_url = get_env("GENIE_SPACE_URL")

# `streamlit.components.v1.iframe` is the supported way to embed iframes
# in a Streamlit app. `st.iframe` does NOT exist; using it raises
# AttributeError. `scrolling=True` lets users scroll inside the iframe
# when conversation history grows beyond the viewport.
components.iframe(src=genie_url, height=1100, scrolling=True)
