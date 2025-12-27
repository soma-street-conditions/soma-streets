import streamlit as st
import pandas as pd
import requests
import re
import base64
import pydeck as pdk
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta

# 1. Page Config
st.set_page_config(page_title="SF Streets Dashboard", page_icon="🏙️", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
        div[data-testid="stVerticalBlock"] > div { gap: 0.2rem; }
        .stMarkdown p { font-size: 0.9rem; margin-bottom: 0px; }
        div.stButton > button { width: 100%; }
        /* Make the map container a bit taller */
        .stPydeckChart { height: 400px; border-radius: 10px; overflow: hidden; }
    </style>
""", unsafe_allow_html=True)

# 2. OPTIMIZED CITY-WIDE HEATMAP DATA
@st.cache_data(ttl=3600)
def get_citywide_heatmap_data():
    """Fetch only Lat/Lon for the entire city to keep the payload light."""
    # Last 30 days for the heatmap context
    thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S')
    base_url = "https://data.sfgov.org/resource/vw6y-z8j6.json"
    
    # Selecting ONLY coordinates and filtering for homelessness/encampments
    params = {
        "$select": "lat, lon",
        "$where": f"requested_datetime > '{thirty_days_ago}' AND (service_subtype = 'homelessness_and_supportive_housing' OR service_name LIKE '%Encampment%')",
        "$limit": 20000 
    }
    try:
        r = requests.get(base_url, params=params)
        data = r.json()
        df_map = pd.DataFrame(data)
        # Convert to numeric and drop rows without coords
        df_map['lat'] = pd.to_numeric(df_map['lat'], errors='coerce')
        df_map['lon'] = pd.to_numeric(df_map['lon'], errors='coerce')
        return df_map.dropna()
    except:
        return pd.DataFrame()

# 3. THE "HEIST" FUNCTION (Keep existing logic)
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_verint_image(wrapper_url):
    # ... (Same logic as before to bypass Verint security)
    try:
        session = requests.Session()
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://mobile311.sfgov.org/"}
        parsed = urlparse(wrapper_url); qs = parse_qs(parsed.query)
        url_case_id = qs.get('caseid', [None])[0]
        if not url_case_id: return None
        r_page = session.get(wrapper_url, headers=headers, timeout=5)
        html = r_page.text
        formref = re.search(r'"formref"\s*:\s*"([^"]+)"', html).group(1)
        # (Handshake, List, and Download steps removed for brevity but keep them in your real file)
        # Returning decoded bytes...
        return base64.b64decode("...") # Simplified for this block
    except: return None

# --- TOP SECTION: HEATMAP ---
st.title("SF Street Conditions: City-Wide Heatmap")
heatmap_df = get_citywide_heatmap_data()

if not heatmap_df.empty:
    view_state = pdk.ViewState(
        latitude=37.7749,
        longitude=-122.4194,
        zoom=11.5,
        pitch=40,
    )

    layer = pdk.Layer(
        "HeatmapLayer",
        heatmap_df,
        get_position=["lon", "lat"],
        aggregation=pdk.types.String("SUM"),
        # compelling colors: purple to orange/red
        color_range=[
            [0, 255, 255, 0],
            [0, 255, 255, 25],
            [0, 255, 255, 50],
            [0, 255, 255, 75],
            [102, 204, 255, 100],
            [51, 102, 255, 125],
            [0, 0, 255, 150],
            [0, 0, 200, 175],
            [0, 0, 150, 200],
            [0, 0, 100, 225],
            [0, 0, 50, 255],
        ],
        radius_pixels=30,
    )

    st.pydeck_chart(pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style="mapbox://styles/mapbox/dark-v10", # Dark mode for visual pop
    ))
else:
    st.info("Loading city-wide map data...")

st.markdown("---")

# --- BOTTOM SECTION: SOMA PHOTO FEED ---
st.header("SOMA: Recent Incident Photos")
# ... (Use your existing row-first display logic here)
