import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# 1. Page Config
st.set_page_config(page_title="SOMA Streets", page_icon="🏙️", layout="wide")

# Header
st.header("SOMA: Recent Street Conditions")
st.write("Live feed of 'General Requests' and 'Encampments' (last 90 days).")
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
    """
    Extracts URL and checks if it ends in a valid image extension.
    Returns None if invalid.
    """
    if not media_item:
        return None
    
    # Extract string from dict if necessary
    url = None
    if isinstance(media_item, dict):
        url = media_item.get('url')
    elif isinstance(media_item, str):
        url = media_item
        
    if not url:
        return None

    # Check extension (ignoring query params like ?token=123)
    clean_url = url.split('?')[0].lower()
    valid_exts = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')
    
    if clean_url.endswith(valid_exts):
        return url
    return None

# 6. Display Feed
if not df.empty:
    cols = st.columns(4)
    display_count = 0  # Counter to ensure grid fills evenly
    
    for index, row in df.iterrows():
        # Validate the image BEFORE trying to display
        image_url = get_valid_image_url(row.get('media_url'))
        
        # If valid, show the card
        if image_url:
            # Determine which column to place this card in
            col_index = display_count % 4
            
            with cols[col_index]:
                with st.container(border=True):
                    
                    # Display Image
                    st.image(image_url, use_container_width=True)
                    
                    # Header
                    st.subheader(f"{row.get('service_name', 'Report')}")
                    
                    # Date & Map Link
                    if 'requested_datetime' in row:
                        date_str = pd.to_datetime(row['requested_datetime']).strftime('%b %d')
                    else:
                        date_str = "Unknown"
                    
                    address = row.get('address', 'Location N/A')
                    map_url = f"https://www.google.com/maps/search/?api=1&query={address.replace(' ', '+')}"
                    
                    st.markdown(f"**{date_str}** | [{address}]({map_url})")
                    
                    # Status
                    status = row.get('status_description', 'Open')
                    if status == 'Open':
                        st.warning(f"Status: {status}")
                    else:
                        st.success(f"Status: {status}")

                    # Smart Notes
                    raw_note = row.get('status_notes', '')
                    if pd.notna(raw_note):
                        if raw_note.strip().lower() != status.lower():
                            st.caption(f"📝 {raw_note}")
            
            # Increment counter only if we actually displayed a card
            display_count += 1
            
    if display_count == 0:
        st.info("No valid images found in the filtered results.")

else:
    st.info("No records found.")

st.markdown("---")
st.caption("Data source: DataSF 311 Cases. Updates automatically.")
