import streamlit as st
import pandas as pd
import requests
import re
import base64
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta

# 1. Page Config
st.set_page_config(page_title="SOMA Streets", page_icon="🏙️", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
        div[data-testid="stVerticalBlock"] > div { gap: 0.2rem; }
        .stMarkdown p { font-size: 0.9rem; margin-bottom: 0px; }
        div.stButton > button { width: 100%; }
    </style>
""", unsafe_allow_html=True)

# 2. THE "HEIST" FUNCTION
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
        if r_page.status_code != 200: return None
        html = r_page.text

        formref_match = re.search(r'"formref"\s*:\s*"([^"]+)"', html)
        if not formref_match: return None
        formref = formref_match.group(1)
        
        csrf_match = re.search(r'name="_csrf_token"\s+content="([^"]+)"', html)
        csrf_token = csrf_match.group(1) if csrf_match else None

        # API Handshake
        try:
            citizen_url = "https://sanfrancisco.form.us.empro.verintcloudservices.com/api/citizen?archived=Y&preview=false&locale=en"
            headers["Referer"] = r_page.url
            headers["Origin"] = "https://sanfrancisco.form.us.empro.verintcloudservices.com"
            if csrf_token: headers["X-CSRF-TOKEN"] = csrf_token
            r_handshake = session.get(citizen_url, headers=headers, timeout=5)
            if 'Authorization' in r_handshake.headers:
                headers["Authorization"] = r_handshake.headers['Authorization']
        except: pass

        # Request File List
        api_base = "https://sanfrancisco.form.us.empro.verintcloudservices.com/api/custom"
        headers["Content-Type"] = "application/json"
        nested_payload = {
            "data": {"caseid": str(url_case_id), "formref": formref},
            "name": "download_attachments", "email": "", "xref": "", "xref1": "", "xref2": ""
        }
        
        r_list = session.post(f"{api_base}?action=get_attachments_details&actionedby=&loadform=true&access=citizen&locale=en", json=nested_payload, headers=headers, timeout=5)
        if r_list.status_code != 200: return None
        
        files_data = r_list.json()
        filename_str = files_data.get('data', {}).get('formdata_filenames', "")
        if not filename_str: return None
        
        target_filename = None
        for fname in filename_str.split(';'):
            fname = fname.strip()
            if not fname: continue
            f_lower = fname.lower()
            if any(x in f_lower for x in ['m.jpg', '_map.jpg', '_map.jpeg']): continue
            if f_lower.endswith(('.jpg', '.jpeg', '.png')):
                target_filename = fname
                break
        
        if not target_filename: return None

        # Download and Decode
        download_payload = nested_payload.copy()
        download_payload["data"]["filename"] = target_filename
        r_image = session.post(f"{api_base}?action=download_attachment&actionedby=&loadform=true&access=citizen&locale=en", json=download_payload, headers=headers, timeout=5)
        
        if r_image.status_code == 200:
            b64_data = r_image.json().get('data', {}).get('txt_file', "")
            if "," in b64_data: b64_data = b64_data.split(",")[1]
            return base_64_bytes := base64.b64decode(b64_data)
            
    except: return None
    return None

# 3. MAIN APP LOGIC
st.header("SOMA: Street Conditions Dashboard")
st.write("Daily feed of homelessness and encampment reports.")

if 'limit' not in st.session_state: st.session_state.limit = 400

@st.cache_data(ttl=300)
def get_311_data(limit):
    ninety_days_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%S')
    base_url = "https://data.sfgov.org/resource/vw6y-z8j6.json"
    params = {
        "$where": f"analysis_neighborhood = 'South of Market' AND requested_datetime > '{ninety_days_ago}' AND media_url IS NOT NULL AND (service_subtype = 'homelessness_and_supportive_housing' OR service_name LIKE '%Encampment%')",
        "$order": "requested_datetime DESC", "$limit": limit
    }
    r = requests.get(base_url, params=params)
    return pd.DataFrame(r.json()) if r.status_code == 200 else pd.DataFrame()

df = get_311_data(st.session_state.limit)

if not df.empty:
    cols = st.columns(4)
    display_count = 0
    
    for _, row in df.iterrows():
        if 'duplicate' in str(row.get('status_notes', '')).lower(): continue
        
        url = row['media_url'].get('url') if isinstance(row['media_url'], dict) else row['media_url']
        img_content = None
        
        # Determine how to fetch the image
        if any(ext in str(url).lower() for ext in ['.jpg', '.jpeg', '.png']):
            img_content = url # Standard direct URL
        elif "verintcloudservices" in str(url):
            img_content = fetch_verint_image(url) # Protected Verint URL

        if img_content:
            with cols[display_count % 4]:
                with st.container(border=True):
                    st.image(img_content, use_container_width=True)
                    date_str = pd.to_datetime(row['requested_datetime']).strftime('%b %d, %I:%M %p')
                    address = row.get('address', 'SOMA').split(',')[0]
                    st.markdown(f"**{date_str}** | {address}")
            display_count += 1

    if st.button("Load More"):
        st.session_state.limit += 400
        st.rerun()
