# =============================================================================
# CONFIGURATION FILE: keys.py (now also config.py)
# =============================================================================
#
# Think of this as the settings page on an app.
# You only need to fill in the bits you actually want to use.
#
# For UK geocoding, you DO NOT need any API keys at all if you
# download and build the local postcode database.
#
# Only fill in the fallback services if you also want to handle
# non-UK addresses or if your local database hasn't been built yet.
# =============================================================================


# --- PRIMARY LOOKUP (no key needed) ---
# The Ordnance Survey Code-Point Open data is free and keyless.
# After the database is built, every UK postcode lookup happens locally.


# --- FALLBACK 1: Nominatim (OpenStreetMap) ---
# This is completely free. The only requirement is a polite "user_agent".
# It is like knocking on a door and saying "Hi, it's me, I just want
# to ask one quick question". The user_agent is how you introduce yourself.
#
# Please set this to your organisation email address or a descriptive string.
# (Nominatim can block you if you send a million requests without introducing yourself)
n_user = ""


# --- FALLBACK 2: OpenMapQuest ---
# This used to be the old script's favourite.
# You can leave this blank if you are only doing UK postcodes.
# If you need it for non-UK addresses, get a free key from:
#     https://developer.mapquest.com/
omq_api = ""


# --- FALLBACK 3: Bing (not recommended for most users) ---
# This is a paid service for heavy usage. If you have one, put it here.
# bing_api = ""


# --- FALLBACK 4: OpenCage ---
# Supports global geocoding but requires a paid plan for heavy usage.
# Get a key from: https://opencagedata.com/
# oc_api = ""


# --- FALLBACK 5: Google V3 ---
# This costs money per lookup. Usually only used when accuracy is critical.
# g3_api = ""
