import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# 1. Page Config: Switch to 'wide' to fit 4 columns
st.set_page_config(page_title="SOMA Streets", page_icon="🏙️", layout="wide")

# Title
st.header("SOMA: Recent Street Conditions")
st.write("Live feed of 'General Requests' and 'Encampments' (last 90 days).")
st.markdown("---")

# Calculate Date (90 days ago)
ninety_days_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%S')

# SF Data API Endpoint
base_url = "https://data.sfgov.org/resource/vw6y-z8j6.json"

# Construct the Query
params = {
    "$where": f"analysis_neighborhood = 'South of Market' AND requested_datetime > '{ninety_days_ago}' AND media_url IS NOT NULL AND (service_name LIKE '%General Request%' OR service_name LIKE '%Encampment%')",
    "$order": "requested_datetime DESC",
    "$limit": 200
}

# Fetch Data
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

# Display the Feed
if not df.empty:
    # 2. Define 4 columns for the grid
    cols = st.columns(4)
    
    for index, row in df.iterrows():
        # Cycle through columns: 0, 1, 2, 3, 0, 1...
        with cols[index % 4]:
            with st.container(border=True):
                
                # --- Image Handling ---
                media_item = row.get('media_url')
                image_url = None
                if isinstance(media_item, dict):
                    image_url = media_item.get('url')
                elif isinstance(media_item, str):
                    image_url = media_item

                if image_url:
                    st.image(image_url, use_container_width=True)
                
                # --- Header ---
                st.subheader(f"{row.get('service_name', 'Report')}")
                
                # --- Date & Clickable Address ---
                if 'requested_datetime' in row:
                    date_str = pd.to_datetime(row['requested_datetime']).strftime('%b %d')
                else:
                    date_str = "Unknown"
                
                address = row.get('address', 'Location N/A')
                # Standard Google Maps Query Link
                map_url = f"https://www.google.com/maps/search/?api=1&query={address.replace(' ', '+')}"
                
                st.markdown(f"**{date_str}** | [{address}]({map_url})")
                
                # --- Status Badge ---
                status = row.get('status_description', 'Open')
                if status == 'Open':
                    st.warning(f"Status: {status}")
                else:
                    st.success(f"Status: {status}")

                # --- Smart Notes ---
                raw_note = row.get('status_notes', '')
                if pd.notna(raw_note):
                    if raw_note.strip().lower() != status.lower():
                        st.caption(f"📝 {raw_note}")
else:
    st.info("No photos found in the last 90 days matching these criteria.")

st.markdown("---")
st.caption("Data source: DataSF 311 Cases. Updates automatically.")
