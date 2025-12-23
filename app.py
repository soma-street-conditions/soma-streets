import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# 1. Page Config
st.set_page_config(page_title="SOMA Streets", page_icon="🏙️", layout="wide")

# --- NO CRAWL & STYLING ---
st.markdown("""
    <style>
        div[data-testid="stVerticalBlock"] > div { gap: 0.2rem; }
        .stMarkdown p { font-size: 0.9rem; margin-bottom: 0px; }
        div.stButton > button { width: 100%; }
        .private-box {
            background-color: #f0f2f6;
            border: 1px dashed #999;
            border-radius: 5px;
            padding: 40px 10px;
            text-align: center;
            color: #555;
            margin-bottom: 10px;
            font-size: 0.9em;
        }
    </style>
    <meta name="robots" content="noindex, nofollow">
""", unsafe_allow_html=True)

# 2. Session State for "Load More"
if 'limit' not in st.session_state:
    st.session_state.limit = 300

# Header
st.header("SOMA: Recent Street Conditions")
st.write("Live feed of 'Homeless Concerns' and 'Encampments' in SOMA via 311.")
st.markdown("Download the Solve SF App to report your concerns to the City of San Francisco. ([iOS](https://apps.apple.com/us/app/solve-sf/id6737751237) | [Android](https://play.google.com/store/apps/details?id=com.woahfinally.solvesf))")
st.markdown("---")

# 3. Date & API Setup
ninety_days_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%dT%H:%M:%S')
base_url = "https://data.sfgov.org/resource/vw6y-z8j6.json"

# 4. Query
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

# 6. SCRAPER FUNCTION: "Unwrap" the Verint Page
@st.cache_data(ttl=3600) # Cache the scraped URL for 1 hour
def extract_image_from_verint(wrapper_url):
    """
    Visits the Verint 'View Attachments' page and extracts the first real image URL.
    """
    try:
        # Fake a browser visit so the server doesn't block us
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(wrapper_url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all images
            images = soup.find_all('img')
            
            for img in images:
                src = img.get('src')
                if src:
                    # Filter out tiny icons or logos if necessary
                    # Usually, the main photo is a .jpg or .jpeg
                    if any(x in src.lower() for x in ['.jpg', '.jpeg', '.png']):
                        # If the src is relative (starts with /), append the domain
                        if src.startswith('/'):
                            # Base domain from your screenshot
                            return "https://sanfrancisco.form.us.empro.verintcloudservices.com" + src
                        return src
        return None
    except:
        return None

# 7. Helper: Router
def get_display_url(media_item):
    """
    Returns (final_url, is_viewable)
    """
    if not media_item: return None, False
    
    url = media_item.get('url') if isinstance(media_item, dict) else media_item
    if not url: return None, False
    
    clean_url = url.split('?')[0].lower()
    
    # Case A: Standard Image (Public Cloud)
    if clean_url.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')):
        return url, True
        
    # Case B: Verint Portal (Wrapper Page)
    if "download_attachments" in clean_url:
        # Try to unwrap it!
        extracted_src = extract_image_from_verint(url)
        if extracted_src:
            return extracted_src, True # Success! We found the inner image
        else:
            return url, False # Failed to extract, fall back to "View Link" button
            
    return None, False

# 8. Display Feed
if not df.empty:
    cols = st.columns(4)
    display_count = 0
    
    for index, row in df.iterrows():
        notes = str(row.get('status_notes', '')).lower()
        if 'duplicate' in notes:
            continue

        # Get the URL (either direct or extracted)
        full_url, is_viewable = get_display_url(row.get('media_url'))
        
        if full_url:
            col_index = display_count % 4
            
            with cols[col_index]:
                with st.container(border=True):
                    
                    if is_viewable:
                        st.image(full_url, use_container_width=True)
                    else:
                        # Fallback if extraction failed
                        st.markdown(f"""
                            <div class="private-box">
                                📸 <b>Image Link</b><br>
                                <span style="font-size: 0.8em">Click to view on Portal</span>
                            </div>
                        """, unsafe_allow_html=True)
                        st.markdown(f"[Open Image Page]({full_url})")

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
    
    st.markdown("---")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if st.button(f"Load More Records (Current: {st.session_state.limit})"):
            st.session_state.limit += 300
            st.rerun()

else:
    st.info("No records found.")

st.markdown("---")
st.caption("Data source: [DataSF | Open Data Portal](https://data.sfgov.org/City-Infrastructure/311-Cases/vw6y-z8j6/about_data)")
