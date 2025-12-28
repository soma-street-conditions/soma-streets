import streamlit as st
import pandas as pd
import requests
import re
import base64
import pydeck as pdk
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta

# ------------------------------------------------------------------
# 1. CONFIGURATION & CSS
# ------------------------------------------------------------------
st.set_page_config(page_title="SF Street Conditions", page_icon="⚠️", layout="wide")

st.markdown("""
    <style>
        div[data-testid="stVerticalBlock"] > div { gap: 0.5rem; }
        h1 { margin-bottom: 0px; padding-bottom: 0px; }
        h3 { margin-top: 20px; color: #ff4b4b; } 
        .stMarkdown p { font-size: 1rem; line-height: 1.5; color: #e0e0e0; }
        
        .mission-box {
            background-color: #262730;
            border-left: 5px solid #ff4b4b;
            padding: 20px;
            margin-bottom: 30px;
            border-radius: 5px;
        }
        .stPydeckChart { height: 600px; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
        div.stButton > button { width: 100%; border-radius: 8px; }
    </style>
    <meta name="robots" content="noindex, nofollow">
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 2. DATA FETCHING: HEATMAP
# ------------------------------------------------------------------
@st.cache_data(ttl=3600)
def get_citywide_heatmap_data():
    days_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%S')
    base_url = "https://data.sfgov.org/resource/vw6y-z8j6.json"
    params = {
        "$select": "lat, long", 
        "$where": f"requested_datetime > '{days_ago}' AND (service_subtype LIKE '%homelessness%' OR service_name LIKE '%Encampment%')",
        "$limit": 30000
    }
    try:
        r = requests.get(base_url, params=params, timeout=30)
        if r.status_code != 200: return pd.DataFrame()
        df = pd.DataFrame(r.json())
        if 'lat' in df.columns and 'long' in df.columns:
            df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
            df['lon'] = pd.to_numeric(df['long'], errors='coerce')
            return df.dropna()
        else: return pd.DataFrame()
    except: return pd.DataFrame()

# ------------------------------------------------------------------
# 3. DATA FETCHING: VERINT DECODER
# ------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_verint_image(wrapper_url):
    try:
        session = requests.Session()
        headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", "Referer": "https://mobile311.sfgov.org/" }
        parsed = urlparse(wrapper_url); qs = parse_qs(parsed.query)
        url_case_id = qs.get('caseid', [None])[0]
        if not url_case_id: return None
        r_page = session.get(wrapper_url, headers=headers, timeout=5)
        html = r_page.text
        formref = re.search(r'"formref"\s*:\s*"([^"]+)"', html).group(1)
        csrf = re.search(r'name="_csrf_token"\s+content="([^"]+)"', html)
        csrf_token = csrf.group(1) if csrf else None
        try:
            headers["X-CSRF-TOKEN"] = csrf_token
            r_hand = session.get("https://sanfrancisco.form.us.empro.verintcloudservices.com/api/citizen?archived=Y&preview=false&locale=en", headers=headers, timeout=5)
            if 'Authorization' in r_hand.headers: headers["Authorization"] = r_hand.headers['Authorization']
        except: pass
        api_base = "https://sanfrancisco.form.us.empro.verintcloudservices.com/api/custom"
        payload = { "data": {"caseid": str(url_case_id), "formref": formref}, "name": "download_attachments" }
        r_list = session.post(f"{api_base}?action=get_attachments_details&access=citizen", json=payload, headers=headers, timeout=5)
        filename_str = r_list.json().get('data', {}).get('formdata_filenames', "")
        target = next((f.strip() for f in filename_str.split(';') if f.strip() and not any(x in f.lower() for x in ['m.jpg', '_map'])), None)
        if not target: return None
        payload["data"]["filename"] = target
        r_img = session.post(f"{api_base}?action=download_attachment&access=citizen", json=payload, headers=headers, timeout=5)
        b64 = r_img.json().get('data', {}).get('txt_file', "").split(",")[-1]
        return base64.b64decode(b64)
    except: return None

# ------------------------------------------------------------------
# 4. SOMA DATA FETCHING
# ------------------------------------------------------------------
if 'limit' not in st.session_state: st.session_state.limit = 400

@st.cache_data(ttl=300)
def get_soma_data(limit):
    days_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%S')
    base_url = "https://data.sfgov.org/resource/vw6y-z8j6.json"
    params = {
        "$where": f"analysis_neighborhood = 'South of Market' AND requested_datetime > '{days_ago}' AND media_url IS NOT NULL AND (service_subtype = 'homelessness_and_supportive_housing' OR service_name LIKE '%Encampment%')",
        "$order": "requested_datetime DESC", "$limit": limit
    }
    r = requests.get(base_url, params=params)
    return pd.DataFrame(r.json()) if r.status_code == 200 else pd.DataFrame()

# ------------------------------------------------------------------
# 5. UI LAYOUT
# ------------------------------------------------------------------
st.title("San Francisco Street Conditions Monitor")
st.markdown("### The Reality of Our Streets")

st.markdown("""
<div class="mission-box">
    <b>Objective:</b> To provide City Stakeholders with real-time, undeniable visibility into the unsafe and unsanitary conditions residents face daily.<br><br>
    The data below highlights the direct result of current policies where individuals are not effectively compelled into existing services, resulting in widespread encampments and hazardous street conditions.
</div>
""", unsafe_allow_html=True)

# --- MAP SECTION ---
st.header("1. City-Wide Scale")
st.markdown("""
This map visualizes the density of **Homeless Concerns** and **Encampment** reports across San Francisco over the **last 90 days**. 
Higher columns indicate a higher concentration of reports in that specific block.
""")

map_data = get_citywide_heatmap_data()

if isinstance(map_data, pd.DataFrame) and not map_data.empty:
    view_state = pdk.ViewState(
        latitude=37.765, longitude=-122.42, zoom=11.8, pitch=25, bearing=0
    )

    hex_layer = pdk.Layer(
        "HexagonLayer",
        map_data,
        get_position=["lon", "lat"],
        radius=40,
        elevation_scale=8,
        elevation_range=[0, 1000],
        pickable=True,
        extruded=True,
        coverage=1,
        opacity=0.6,
        color_range=[
            [255, 237, 160], [254, 178, 76], [253, 141, 60],
            [227, 26, 28], [189, 0, 38]
        ],
    )

    label_data = [
        {"name": "SOMA", "lat": 37.778, "lon": -122.408},
        {"name": "TENDERLOIN", "lat": 37.784, "lon": -122.414},
        {"name": "MISSION", "lat": 37.760, "lon": -122.419},
        {"name": "CIVIC CENTER", "lat": 37.779, "lon": -122.416}
    ]
    
    text_layer = pdk.Layer(
        "TextLayer",
        label_data,
        get_position=["lon", "lat"],
        get_text="name",
        get_color=[255, 255, 255],
        get_size=16,
        get_alignment_baseline="'bottom'",
        font_weight="bold"
    )

    # --- FIX: USE EXPLICIT VIEW CONTROLLER ---
    # This works on older Pydeck versions where "controller=True" causes a crash.
    view = pdk.View(type="MapView", controller=True)

    st.pydeck_chart(pdk.Deck(
        layers=[hex_layer, text_layer],
        initial_view_state=view_state,
        map_style=pdk.map_styles.CARTO_DARK,
        views=[view], # Explicitly defining the view with controller enabled
        tooltip={"text": "Reports in this block: {elevationValue}"}
    ))
elif isinstance(map_data, str):
    st.error(map_data)
else:
    st.warning("Loading map data... If this persists, the API may be busy.")

st.markdown("---")

# --- SOMA PHOTOS SECTION ---
st.header("2. On-the-Ground Reality: SOMA")
st.markdown("""
Below is a daily feed of resident-submitted evidence from the **South of Market** neighborhood. 
These photos document the specific locations where intervention is most urgently needed.
""")

df = get_soma_data(st.session_state.limit)

if not df.empty:
    display_list = []
    for _, row in df.iterrows():
        if 'duplicate' in str(row.get('status_notes', '')).lower(): continue
        url_data = row.get('media_url')
        url = url_data.get('url') if isinstance(url_data, dict) else url_data
        
        img_content = None
        if any(ext in str(url).lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
            img_content = url
        elif "verintcloudservices" in str(url):
            img_content = fetch_verint_image(url)
            
        if img_content:
            display_list.append({'content': img_content, 'row': row})

    batch_size = 4
    for i in range(0, len(display_list), batch_size):
        cols = st.columns(batch_size)
        for j in range(batch_size):
            if i + j < len(display_list):
                item = display_list[i+j]
                with cols[j]:
                    with st.container(border=True):
                        st.image(item['content'], width="stretch")
                        date_str = pd.to_datetime(item['row']['requested_datetime']).strftime('%b %d, %I:%M %p')
                        address = item['row'].get('address', 'SOMA').split(',')[0]
                        map_url = f"https://www.google.com/maps/search/?api=1&query={item['row'].get('address', '').replace(' ', '+')}"
                        st.markdown(f"**{date_str}** | [{address}]({map_url})")

    st.markdown("---")
    if st.button("Load More Records"):
        st.session_state.limit += 400
        st.rerun()

st.markdown("---")
with st.expander("Methodology & Data Transparency"):
    st.markdown("""
    **Data Sources:**
    * **Map:** City-wide reports (Lat/Long) from the last 90 days.
    * **Photos:** SOMA-specific reports from the last 90 days.
    
    **Technical Note:**
    Images submitted via the 'Web' source are hosted on a secure enterprise portal. This application uses a custom session handshake to decrypt and display these images alongside public mobile reports.
    """)
