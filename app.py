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
        /* Tighter spacing */
        div[data-testid="stVerticalBlock"] > div { gap: 0.5rem; }
        
        /* Typography adjustments */
        h1 { margin-bottom: 0px; padding-bottom: 0px; }
        h3 { margin-top: 20px; color: #ff4b4b; } 
        .stMarkdown p { font-size: 1rem; line-height: 1.5; color: #e0e0e0; }
        
        /* Mission Statement Box */
        .mission-box {
            background-color: #262730;
            border-left: 5px solid #ff4b4b;
            padding: 20px;
            margin-bottom: 30px;
            border-radius: 5px;
        }
        
        /* Map container styling */
        .stPydeckChart { border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
        
        /* Button styling */
        div.stButton > button { width: 100%; border-radius: 8px; }
    </style>
    <meta name="robots" content="noindex, nofollow">
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 2. DATA FETCHING (Keep all existing robust logic)
# ------------------------------------------------------------------
@st.cache_data(ttl=3600)
def get_citywide_heatmap_data():
    days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S')
    base_url = "https://data.sfgov.org/resource/vw6y-z8j6.json"
    params = {
        "$select": "lat, lon",
        "$where": f"requested_datetime > '{days_ago}' AND (service_subtype = 'homelessness_and_supportive_housing' OR service_name LIKE '%Encampment%')",
        "$limit": 25000
    }
    try:
        r = requests.get(base_url, params=params, timeout=10)
        if r.status_code != 200: return pd.DataFrame()
        df = pd.DataFrame(r.json())
        df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
        df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
        return df.dropna()
    except: return pd.DataFrame()

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
        csrf_match = re.search(r'name="_csrf_token"\s+content="([^"]+)"', html)
        csrf_token = csrf_match.group(1) if csrf_match else None
        try:
            citizen_url = "https://sanfrancisco.form.us.empro.verintcloudservices.com/api/citizen?archived=Y&preview=false&locale=en"
            headers["Referer"] = r_page.url
            headers["Origin"] = "https://sanfrancisco.form.us.empro.verintcloudservices.com"
            if csrf_token: headers["X-CSRF-TOKEN"] = csrf_token
            r_handshake = session.get(citizen_url, headers=headers, timeout=5)
            if 'Authorization' in r_handshake.headers: headers["Authorization"] = r_handshake.headers['Authorization']
        except: pass
        api_base = "https://sanfrancisco.form.us.empro.verintcloudservices.com/api/custom"
        headers["Content-Type"] = "application/json"
        nested_payload = {
            "data": {"caseid": str(url_case_id), "formref": formref},
            "name": "download_attachments", "email": "", "xref": "", "xref1": "", "xref2": ""
        }
        r_list = session.post(f"{api_base}?action=get_attachments_details&actionedby=&loadform=true&access=citizen&locale=en", json=nested_payload, headers=headers, timeout=5)
        files_data = r_list.json()
        filename_str = files_data.get('data', {}).get('formdata_filenames', "")
        target_filename = None
        for fname in filename_str.split(';'):
            fname = fname.strip()
            if fname and not any(x in fname.lower() for x in ['m.jpg', '_map.jpg']):
                target_filename = fname; break
        if not target_filename: return None
        download_payload = nested_payload.copy()
        download_payload["data"]["filename"] = target_filename
        r_image = session.post(f"{api_base}?action=download_attachment&actionedby=&loadform=true&access=citizen&locale=en", json=download_payload, headers=headers, timeout=5)
        if r_image.status_code == 200:
            b64_data = r_image.json().get('data', {}).get('txt_file', "").split(",")[-1]
            return base64.b64decode(b64_data)
    except: return None
    return None

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
# 3. NARRATIVE HEADER
# ------------------------------------------------------------------
st.title("San Francisco Street Conditions Monitor")
st.markdown("### The Reality of Our Streets")

st.markdown("""
<div class="mission-box">
    <b>Objective:</b> To provide City Stakeholders with real-time, undeniable visibility into the unsafe and unsanitary conditions residents face daily.<br><br>
    The data below highlights the direct result of current policies where individuals are not effectively compelled into existing services, resulting in widespread encampments and hazardous street conditions.
</div>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 4. SECTION: CITY-WIDE CONTEXT (HEATMAP)
# ------------------------------------------------------------------
st.header("1. City-Wide Scale")
st.markdown("""
This map visualizes the density of **Homeless Concerns** and **Encampment** reports across San Francisco over the last 30 days. 
It demonstrates that while specific neighborhoods bear a heavy load, this is a systemic city-wide crisis requiring broad intervention.
""")

heatmap_df = get_citywide_heatmap_data()

if not heatmap_df.empty:
    st.pydeck_chart(pdk.Deck(
        map_style="mapbox://styles/mapbox/dark-v10",
        initial_view_state=pdk.ViewState(latitude=37.7749, longitude=-122.4194, zoom=11.5, pitch=45),
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
else:
    st.info("Loading city-wide data...")

st.markdown("---")

# ------------------------------------------------------------------
# 5. SECTION: ON-THE-GROUND REALITY (SOMA FEED)
# ------------------------------------------------------------------
st.header("2. On-the-Ground Reality: SOMA")
st.markdown("""
Below is a daily feed of resident-submitted evidence from the **South of Market** neighborhood. 
These photos document the specific locations where intervention is most urgently needed.
""")

df = get_soma_data(st.session_state.limit)

if not df.empty:
    display_list = []
    
    # Pre-process & filter
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

    # Row-first grid display (Mobile Optimized)
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

# ------------------------------------------------------------------
# 6. FOOTER
# ------------------------------------------------------------------
st.markdown("---")
with st.expander("Methodology & Data Transparency"):
    st.markdown("""
    **Data Sources:**
    * **Map:** City-wide reports (Lat/Lon only) from the last 30 days via DataSF.
    * **Photos:** SOMA-specific reports from the last 90 days.
    
    **Technical Note:**
    Images submitted via the 'Web' source are hosted on a secure enterprise portal. This application uses a custom session handshake to decrypt and display these images alongside public mobile reports to ensure a complete record of conditions.
    """)
