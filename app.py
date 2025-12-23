import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# 1. Page Config
st.set_page_config(page_title="SOMA Streets", page_icon="🏙️", layout="wide")

# Custom CSS
st.markdown("""
    <style>
        div[data-testid="stVerticalBlock"] > div {
            gap: 0.2rem;
        }
        .stMarkdown p {
            font-size: 0.9rem;
            margin-bottom: 0px;
        }
        div.stButton > button {
            width: 100%;
        }
    </style>
""", unsafe_allow_html=True)

# 2. Session State for "Load More"
if 'limit' not in st.session_state:
    st.session_state.limit = 300

# Header
st.header("SOMA: Recent Street Conditions")
st.write("Live feed of conditions in SOMA (last 90 days).")
st.markdown("---")

# 3. Date & API Setup
ninety_days_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%S')
base_url = "https://data.sfgov.org/resource/vw6y-z8j6.json"

# 4. Query (Using dynamic limit)
params = {
    "$where": f"analysis_neighborhood = 'South of Market' AND requested_datetime > '{ninety_days_ago}' AND media_url IS NOT NULL AND (service_name LIKE '%General Request%' OR service_name LIKE '%Encampment%')",
    "$order": "requested_datetime DESC",
    "$limit": st.session_state.limit
}

# 5. Fetch Data
@st.cache_data(ttl=300)
def get_data(query_limit):
    try:
        r = requests.get(base_url, params=params)
        if r.status_code == 200:
            return pd.DataFrame(r.json())
        else:
            return pd.DataFrame()
    except:
        return pd.DataFrame()

df = get_data(st.session_state.limit)

# 6. Helper to Validate Images
def get_valid_image_url(media_item):
    if not media_item: return None
    url = media_item.get('url') if isinstance(media_item, dict) else media_item
    if not url: return None
    clean_url = url.split('?')[0].lower()
    if clean_url.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')):
        return url
    return None

# 7. Display Feed
if not df.empty:
    cols = st.columns(4)
    display_count = 0
    
    for index, row in df.iterrows():
        # --- FILTER: Skip Duplicates ---
        notes = str(row.get('status_notes', '')).lower()
        if 'duplicate' in notes:
            continue

        # --- Validate Image ---
        image_url = get_valid_image_url(row.get('media_url'))
        
        if image_url:
            col_index = display_count % 4
            
            with cols[col_index]:
                with st.container(border=True):
                    
                    # Image
                    st.image(image_url, use_container_width=True)
                    
                    # Metadata
                    if 'requested_datetime' in row:
                        date_str = pd.to_datetime(row['requested_datetime']).strftime('%b %d, %I:%M %p')
                    else:
                        date_str = "?"
                    
                    address = row.get('address', 'Location N/A')
                    short_address = address.split(',')[0] 
                    map_url = f"https://www.google.com/maps/search/?api=1&query={address.replace(' ', '+')}"
                    
                    st.markdown(f"**{date_str}** | [{short_address}]({map_url})")
            
            display_count += 1
            
    if display_count == 0:
        st.info("No images found (duplicates filtered).")
    
    # 8. LOAD MORE BUTTON
    st.markdown("---")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if st.button(f"Load More Records (Current: {st.session_state.limit})"):
            st.session_state.limit += 300
            st.rerun()

else:
    st.info("No records found.")
