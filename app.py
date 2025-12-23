import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# Page Configuration
st.set_page_config(page_title="SoMa Street Stream", page_icon="📸", layout="centered")

# Title and Intro
st.title("📸 SoMa Street Stream")
st.write("Live feed of 'General Requests' and 'Encampments' in SoMa (last 90 days).")
st.markdown("---")

# 1. Calculate Date (90 days ago)
ninety_days_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%S')

# 2. SF Data API Endpoint (311 Cases)
base_url = "https://data.sfgov.org/resource/vw6y-z8j6.json"

# 3. Construct the Query
# We filter for South of Market, specific request types, and ensure photos exist.
params = {
    "$where": f"analysis_neighborhood = 'South of Market' AND requested_datetime > '{ninety_days_ago}' AND media_url IS NOT NULL AND (service_name LIKE '%General Request%' OR service_name LIKE '%Encampment%')",
    "$order": "requested_datetime DESC",
    "$limit": 200
}

# 4. Fetch Data Function
@st.cache_data(ttl=300) # Refreshes data every 5 minutes
def get_data():
    try:
        r = requests.get(base_url, params=params)
        if r.status_code == 200:
            return pd.DataFrame(r.json())
        else:
            return pd.DataFrame()
    except:
        return pd.DataFrame()

# 5. Load Data
df = get_data()

# 6. Display the Feed
if not df.empty:
    for index, row in df.iterrows():
        # Create a card-like container for each item
        with st.container(border=True):
            # The Photo (Full width for scrolling)
            if 'media_url' in row:
                st.image(row['media_url'], use_container_width=True)
            
            # The Info
            st.subheader(f"{row.get('service_name', 'Report')}")
            
            # Date Formatting
            date_str = pd.to_datetime(row['requested_datetime']).strftime('%B %d at %I:%M %p')
            st.caption(f"📅 {date_str} | 📍 {row.get('address', 'Location N/A')}")
            
            # Status
            status = row.get('status_description', 'Open')
            if status == 'Open':
                st.warning(f"Status: {status}")
            else:
                st.success(f"Status: {status}")

            # Description/Notes
            if 'status_notes' in row and pd.notna(row['status_notes']):
                st.markdown(f"**Note:** {row['status_notes']}")
else:
    st.info("No photos found in the last 90 days matching these criteria.")

# Footer
st.markdown("---")
st.caption("Data source: DataSF 311 Cases. Updates every 5 minutes.")