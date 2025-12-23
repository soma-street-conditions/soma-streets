import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# 1. Page Config
st.set_page_config(page_title="SOMA Streets", page_icon="🏙️", layout="wide")

# Custom CSS to reduce padding and tighten the look
st.markdown("""
    <style>
        div[data-testid="stVerticalBlock"] > div {
            gap: 0.2rem;
        }
        .stMarkdown p {
            font-size: 0.9rem;
            margin-bottom: 0px;
        }
    </style>
""", unsafe_allow_html=True)

# Header
st.header("SOMA: Recent Street Conditions")
st.write("Live feed of conditions in SoMa (last 90 days).")
st.markdown("---")

# 2. Date & API Setup
ninety_days_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%S')
base_url = "https://data.sfgov.org/resource/vw6y-z8j6.json"

# 3. Query
params = {
    "$where": f"analysis_neighborhood = 'South of Market' AND requested_datetime > '{ninety_days_ago}' AND media_url IS NOT NULL AND (service_name LIKE '%General Request%' OR service_name LIKE '%Encampment%')",
    "$order": "requested_datetime DESC",
    "$limit": 200
}

# 4. Fetch Data
@st.cache_data(ttl=300)
def get_data():
    try:
        r = requests.get(base_url, params=params)
        if r.status_code == 200:
            return pd.DataFrame(r.json())
        else:
            return pd.DataFrame()
    except:
        return pd.DataFrame()

df = get_data()

# 5. Helper to Validate Images
def get_valid_image_url(media_item):
    if not media_item: return None
    url = media_item.get('url') if isinstance(media_item, dict) else media_item
    if not url: return None
    clean_url = url.split('?')[0].lower()
    if clean_url.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')):
        return url
    return None

# 6. Display Feed
if not df.empty:
    cols = st.columns(4)
    display_count = 0
    
    for index, row in df.iterrows():
        image_url = get_valid_image_url(row.get('media_url'))
        
        if image_url:
            col_index = display_count % 4
            
            with cols[col_index]:
                with st.container(border=True):
                    
                    # 1. The Photo
                    st.image(image_url, use_container_width=True)
                    
                    # 2. Minimal Metadata (Date | Location)
                    if 'requested_datetime' in row:
                        date_str = pd.to_datetime(row['requested_datetime']).strftime('%b %d')
                    else:
                        date_str = "?"
                    
                    address = row.get('address', 'Location N/A')
                    # Shorten address if it's very long to keep lines clean
                    short_address = address.split(',')[0] 
                    map_url = f"https://www.google.com/maps/search/?api=1&query={address.replace(' ', '+')}"
                    
                    # Single clean line of text
                    st.markdown(f"**{date_str}** | [{short_address}]({map_url})")
            
            display_count += 1
            
    if display_count == 0:
        st.info("No valid images found in the filtered results.")

else:
    st.info("No records found.")
