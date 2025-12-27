import streamlit as st
import pandas as pd
import requests
import re
import base64
import pydeck as pdk
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta

# 1. Page Config
st.set_page_config(page_title="SF Street Conditions", page_icon="🏙️", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
        div[data-testid="stVerticalBlock"] > div { gap: 0.2rem; }
        .stMarkdown p { font-size: 0.9rem; margin-bottom: 0px; }
        div.stButton > button { width: 100%; }
        .stPydeckChart { border-radius: 10px; overflow: hidden; }
    </style>
    <meta name="robots" content="noindex, nofollow">
""", unsafe_allow_html=True)

# 2. OPTIMIZED CITY-WIDE HEATMAP DATA
@st.cache_data(ttl=3600)
def get_citywide_heatmap_data():
    thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S')
    base_url = "https://data.sfgov.org/resource/vw6y-z8j6.json"
    
    # Lean fetch: only lat/lon to save memory and bandwidth
    params = {
        "$select": "lat, lon",
        "$where": f"requested_datetime > '{thirty_days_ago}' AND (service_subtype = 'homelessness_and_supportive_housing' OR service_name LIKE '%Encampment%')",
        "$limit": 30000 
    }
    try:
        r = requests.get(base_url, params=params)
        df_map = pd.DataFrame(r.json())
        df_map['lat'] = pd.to_numeric(df_map['lat'], errors='coerce')
        df_map['lon'] = pd.to_numeric(df_map['lon'], errors='coerce')
        return df_map.dropna()
    except:
        return pd.DataFrame()

# 3. THE "HEIST" FUNCTION (Verint Image Decoder)
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_verint_image(wrapper_url):
    try:
        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://mobile311.sfgov.org/",
        }
        parsed = urlparse(wrapper_url)
        qs = parse_qs(parsed.query)
        url_case_id = qs.get('caseid', [None])[0]
        if not url_case_id: return None
        
        r_page = session.get(wrapper_url, headers=headers, timeout=5)
        html = r_page.text
        
        formref = re.search(r'"formref"\s*:\s*"([^"]+)"', html).group(1)
        csrf_token = re.search(r'name="_csrf_token"\s+content="([^"]+)"', html).group(1)

        # Handshake
        citizen_url = "https://sanfrancisco.form.us.empro.verintcloudservices.com/api/citizen?archived=Y&preview=false&locale=en"
        headers["X-CSRF-TOKEN"] = csrf_token
        r_handshake = session.get(citizen_url, headers=headers, timeout=5)
        if 'Authorization' in r_handshake.headers:
            headers["Authorization"] = r_handshake.headers['Authorization']

        # Get Filenames
        api_base = "https://sanfrancisco.form.us.empro.verintcloudservices.com/api/custom"
        headers["Content-Type"] = "application/json"
        payload = {
            "data": {"caseid": str(url_case_id), "formref": formref},
            "name": "download_attachments", "email": "", "xref": "", "xref1": "", "xref2": ""
        }
        
        r_list = session.post(f"{api_base}?action=get_attachments_details&access=citizen", json=payload, headers=headers)
        filename_str = r_list.json().get('data', {}).get('formdata_filenames', "")
        
        target_filename = None
        for fname in filename_str.split(';'):
            fname = fname.strip()
            if fname and not any(x in fname.lower() for x in ['m.jpg', '_map.jpg']):
                target_filename = fname
                break
        
        if not target_filename: return None

        # Download
        payload["data"]["filename"] = target_filename
        r_img = session.post(f"{api_base}?action=download_attachment&access=citizen", json=payload, headers=headers)
        b64_data = r_img.json().get('data', {}).get('txt_file', "").split(",")[-1]
        return base64.b64decode(b64_data)
    except: return None

# --- UI LAYOUT ---
st.title("SF 311: City-Wide Incident Heatmap")
heatmap_df = get_citywide_heatmap_data()

if not heatmap_df.empty:
    st.pydeck_chart(pdk.Deck(
        map_style="mapbox://styles/mapbox/dark-v10",
        initial_view_state=pdk.ViewState(
            latitude=37.7749, longitude=-122.4194, zoom=11.5, pitch=45
        ),
        layers=[
            pdk.Layer(
                "HeatmapLayer",
                heatmap_df,
                get_position=["lon", "lat"],
                auto_highlight=True,
                radius_pixels=40,
                intensity=1,
                threshold=0.05,
                color_range=[
                    [255, 255, 178], [254, 217, 118], [254, 178, 76],
                    [253, 141, 60], [240, 59, 32], [189, 0, 38]
                ],
            )
        ],
    ))

st.markdown("---")
st.header("SOMA: Recent Incident Photos")

if 'limit' not in st.session_state: st.session_state.limit = 400

@st.cache_data(ttl=300)
def get_soma_data(limit):
    ninety_days_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%S')
    base_url = "https://data.sfgov.org/resource/vw6y-z8j6.json"
    params = {
        "$where": f"analysis_neighborhood = 'South of Market' AND requested_datetime > '{ninety_days_ago}' AND media_url IS NOT NULL AND (service_subtype = 'homelessness_and_supportive_housing' OR service_name LIKE '%Encampment%')",
        "$order": "requested_datetime DESC", "$limit": limit
    }
    r = requests.get(base_url, params=params)
    return pd.DataFrame(r.json()) if r.status_code == 200 else pd.DataFrame()

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

    # Row-first grid display
    for i in range(0, len(display_list), 4):
        cols = st.columns(4)
        for j in range(4):
            if i + j < len(display_list):
                item = display_list[i+j]
                with cols[j]:
                    with st.container(border=True):
                        # UPDATED: width="stretch" fixes the 2025 deprecation error
                        st.image(item['content'], width="stretch")
                        date_str = pd.to_datetime(item['row']['requested_datetime']).strftime('%b %d, %I:%M %p')
                        address = item['row'].get('address', 'SOMA').split(',')[0]
                        st.markdown(f"**{date_str}** | {address}")

    if st.button("Load More"):
        st.session_state.limit += 400
        st.rerun()

st.markdown("---")
with st.expander("Methodology & Notes"):
    st.markdown("Heatmap uses 30-day city-wide incident volume. Photo feed uses 90-day SOMA specific records. Verint images decoded via session handshake.")
