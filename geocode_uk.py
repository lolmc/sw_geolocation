#!/usr/bin/env python3
"""
geocode_uk.py
==============
What this script does (in simple terms):
-----------------------------------------
You give it a list of addresses. Think of it as a list of delivery stops for a driver.

For every address, the script tries to find the latitude and longitude
(like a pin on a map). It tries the FASTEST and CHEAPEST way first
(a local file on your computer), then only if that fails does it ask
the internet for help.

Why we do it this way:
- The UK Government gives away all postcode locations for free.
- Searching that local list is INSTANT and costs nothing.
- If an address isn't in that list (maybe it is outside the UK),
  we politely ask the free OpenStreetMap service (Nominatim).
- If even that fails, we try a backup internet service (like OpenMapQuest).

We also write down HOW we found each address (e.g. 'codepoint_open' or 'nominatim')
and the date, so you know how fresh the data is.

Usage:
------
    python geocode_uk.py data.csv

The input CSV must have columns. For UK addresses, we really want:
    - postcode (e.g. 'PL0 1PF')   <-- this is the most important one
    - street
    - city
    - post code (alternative spelling, we fix that for you)

The output file will be named gc_data.csv (or gc_whatever_your_file_is.csv).
It will contain the original data PLUS:
    - lat       (latitude,  the vertical line on a map)
    - lng       (longitude, the horizontal line on a map)
    - geocode_source  (where we got the coordinates from)
    - geocode_date    (when we looked it up)
"""

import csv
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from geopy.geocoders import Nominatim, OpenMapQuest
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# Our little helper that fixes messy postcodes.
import postcode_utils

# Our config file where you put your backup API keys.
import keys


# --- Settings you can change ---
SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"
DB_PATH = DATA_DIR / "uk_postcodes.db"

OUTPUT_COLUMNS = ["lat", "lng", "geocode_source", "geocode_date"]

# How many seconds to sleep between internet requests (to be polite).
# Nominatim asks for AT LEAST 1 second between requests.
RATE_LIMIT_SECONDS = 1.0

# How many times to retry a failed internet request.
MAX_RETRIES = 3

# Bounding box for the UK (simple sanity check).
# Latitude must be between these two numbers.
UK_LAT_MIN, UK_LAT_MAX = 49.8, 60.8
# Longitude must be between these two numbers.
UK_LNG_MIN, UK_LNG_MAX = -8.6, 1.8


def _setup_logging():
    """
    Logging is like keeping a diary of everything the script did.
    If something goes wrong, you can read the diary instead of guessing.
    """
    logging.basicConfig(
        filename="geocode_log.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Also print INFO and above messages to the terminal window.
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    logging.getLogger("").addHandler(console)


class LocalPostcodeDB:
    """
    This class is the wrapper around our local postcode filing cabinet (SQLite).
    Think of it as the friendly librarian who goes to get the book for you.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn = None  # We open the connection only when needed.

    def _connect(self):
        """Open the shelf/database if it is not already open."""
        if self._conn is None:
            import sqlite3

            self._conn = sqlite3.connect(self.db_path)
        return self._conn

    def lookup(self, postcode: str) -> Optional[Tuple[float, float]]:
        """
        Ask the local database: 'Hey, do you know where this postcode lives?'
        
        If it does, it gives back (latitude, longitude).
        If it doesn't, it gives back None (computer for 'I don't know').
        """
        if not self.db_path.exists():
            return None

        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT latitude, longitude FROM postcodes WHERE postcode = ?",
            (postcode.upper(),),
        )
        row = cursor.fetchone()
        if row:
            return float(row[0]), float(row[1])
        return None

    def close(self):
        """Close the filing cabinet so nothing gets corrupted."""
        if self._conn:
            self._conn.close()
            self._conn = None


def _is_uk_coordinate(lat: float, lng: float) -> bool:
    """
    A quick sanity check. If a coordinate is nowhere near the UK,
    something probably went wrong and we should not trust it.
    """
    return UK_LAT_MIN <= lat <= UK_LAT_MAX and UK_LNG_MIN <= lng <= UK_LNG_MAX


def _init_geocoders():
    """
    Prepare the internet-based geocoders as a BACKUP plan.
    We only create them if the keys are provided in keys.py.
    """
    geocoders = []

    # 1. Nominatim (OpenStreetMap)
    # This is completely free BUT you MUST tell it who you are (user_agent).
    # Also you MUST be polite and wait at least 1 second between requests.
    if getattr(keys, "n_user", None):
        geocoders.append(
            ("nominatim", Nominatim(user_agent=keys.n_user, timeout=10))
        )
    else:
        # If you don't have a user agent set, use a sensible default.
        # But in a real organisation you should put your email address in keys.py
        # so Nominatim can contact you if something goes wrong.
        geocoders.append(
            ("nominatim", Nominatim(user_agent="sw_geolocation_uk_script", timeout=10))
        )

    # 2. OpenMapQuest (optional backup, needs an API key)
    if getattr(keys, "omq_api", None) and keys.omq_api != "YOURUNIQUEAPICODEGOESHERE":
        geocoders.append(
            ("openmapquest", OpenMapQuest(api_key=keys.omq_api, timeout=10))
        )

    return geocoders


def _internet_geocode(address_text: str, label: str, geocoders: List[Tuple[str, object]]) -> Optional[Tuple[float, float, str]]:
    """
    This is the 'phone a friend' function.
    
    When our local database doesn't have the postcode,
    we politely ask the internet services one by one until someone answers.
    
    We give each service up to 3 tries, in case the internet is just having a bad day.
    We also wait at least 1 second between requests so we don't get told off.
    
    Returns: (latitude, longitude, source_name) or None if everyone fails.
    """
    for source_name, gcoder in geocoders:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                location = gcoder.geocode(address_text)
                if location:
                    logging.info(f"[{label}] SUCCESS via {source_name}: {address_text}")
                    # Wait before the next request (to be polite to the free service).
                    time.sleep(RATE_LIMIT_SECONDS)
                    return location.latitude, location.longitude, source_name
                else:
                    logging.warning(f"[{label}] {source_name} returned no result for: {address_text}")
            except GeocoderTimedOut:
                logging.warning(f"[{label}] {source_name} timed out (attempt {attempt}/{MAX_RETRIES})")
            except GeocoderServiceError as exc:
                logging.warning(f"[{label}] {source_name} service error (attempt {attempt}/{MAX_RETRIES}): {exc}")
            except Exception as exc:
                logging.error(f"[{label}] {source_name} unexpected error (attempt {attempt}/{MAX_RETRIES}): {exc}")

            # Wait a bit longer before retrying, to give the internet time to recover.
            if attempt < MAX_RETRIES:
                time.sleep(RATE_LIMIT_SECONDS * attempt)

    # If we get here, nobody on the internet could help.
    logging.error(f"[{label}] ALL geocoders failed for: {address_text}")
    return None


def geocode_row(row: pd.Series, local_db: LocalPostcodeDB, geocoders: List[Tuple[str, object]]) -> pd.Series:
    """
    This is the brain for ONE single address row.
    
    Step 1: Try to find a postcode in the row.
    Step 2: If we find one, look it up in the LOCAL database first.
    Step 3: If the local database doesn't know, or there is no postcode,
            try the INTERNET geocoders as a fallback.
    Step 4: Return the result as a little row of new columns.
    """
    # Figure out which column the postcode is hiding in.
    # People might name it 'postcode', 'post code', 'postalCode', etc.
    postcode = None
    for col in ["postcode", "post code", "postalCode", "postal_code", "PostCode"]:
        if col in row and pd.notna(row[col]):
            postcode = str(row[col])
            break

    # --- ATTEMPT 1: Local postcode database ---
    if postcode:
        normalised = postcode_utils.normalise_postcode(postcode)
        if normalised and local_db.db_path.exists():
            local_result = local_db.lookup(normalised)
            if local_result:
                lat, lng = local_result
                logging.info(f"[row {row.name}] FOUND in local DB: {normalised} -> {lat}, {lng}")
                return pd.Series({
                    "lat": lat,
                    "lng": lng,
                    "geocode_source": "codepoint_open",
                    "geocode_date": datetime.now(timezone.utc).isoformat(),
                })

    # --- ATTEMPT 2: Internet geocoding (fallback) ---
    # Build a friendly address sentence from whatever columns we have.
    street = str(row.get("street", "")) if pd.notna(row.get("street")) else ""
    city = str(row.get("city", "")) if pd.notna(row.get("city")) else ""
    address_text = postcode_utils.format_address_street_city_postcode(street, city, postcode)

    if not address_text.strip():
        # If there is literally nothing to search for, give up early.
        logging.warning(f"[row {row.name}] No address information to geocode.")
        return pd.Series({
            "lat": None,
            "lng": None,
            "geocode_source": "no_data",
            "geocode_date": datetime.now(timezone.utc).isoformat(),
        })

    result = _internet_geocode(address_text, f"row {row.name}", geocoders)

    if result:
        lat, lng, source = result
        # Extra sanity check: if we thought this was a UK postcode,
        # lets make sure the internet didn't send us to Australia by mistake.
        if postcode and local_db.db_path.exists():
            if not _is_uk_coordinate(lat, lng):
                logging.warning(
                    f"[row {row.name}] Coordinate {lat},{lng} from {source} looks outside UK. "
                    f"Postcode was: {postcode}"
                )
        return pd.Series({
            "lat": lat,
            "lng": lng,
            "geocode_source": source,
            "geocode_date": datetime.now(timezone.utc).isoformat(),
        })

    # --- Complete failure ---
    logging.error(f"[row {row.name}] FAILED to geocode: {address_text}")
    return pd.Series({
        "lat": None,
        "lng": None,
        "geocode_source": "failed",
        "geocode_date": datetime.now(timezone.utc).isoformat(),
    })


def main(input_csv: str):
    """
    main() is the driver. Like the conductor of an orchestra,
    it tells everyone else when to play and in what order.
    """
    input_path = Path(input_csv)
    output_path = input_path.parent / f"gc_{input_path.name}"

    logging.info("=" * 60)
    logging.info("Starting geocode_uk.py")
    logging.info(f"Input file : {input_path}")
    logging.info(f"Output file: {output_path}")

    # 1. Check the input file exists.
    if not input_path.exists():
        logging.error(f"Input file not found: {input_path}")
        print(f"ERROR: Could not find input file: {input_path}")
        sys.exit(1)

    # 2. Load the CSV into a table we can work with.
    print(f"Reading input file: {input_path}")
    df = pd.read_csv(input_path, dtype=str)
    print(f"Loaded {len(df)} rows.")

    # 3. Set up our local postcode database.
    local_db = LocalPostcodeDB(DB_PATH)
    if not DB_PATH.exists():
        print(
            "\nWARNING: Local postcode database not found.\n"
            "         Run 'python load_codepoint_open.py' first to download it.\n"
            "         Falling back to internet-only geocoding (much slower).\n"
        )
        logging.warning("Local postcode DB not found. Using internet fallback only.")

    # 4. Set up internet geocoders as backup.
    geocoders = _init_geocoders()
    if not geocoders:
        print("WARNING: No internet geocoders configured. Only local database will be used.")
        logging.warning("No internet geocoders configured.")

    # 5. Go through every row and geocode it.
    # We use a list first so we can build a proper DataFrame, then merge it.
    print("Geocoding addresses...")
    results = []
    for idx, row in df.iterrows():
        result_series = geocode_row(row, local_db, geocoders)
        results.append(result_series)

    # 6. Combine the results into a new DataFrame and stick it next to the original.
    results_df = pd.DataFrame(results)
    df = pd.concat([df, results_df], axis=1)

    # 7. Save the final file.
    df.to_csv(output_path, encoding="utf-8", index=False)
    print(f"Done! Results saved to: {output_path}")
    logging.info(f"Finished. Total rows: {len(df)}. Output: {output_path}")
    logging.info("=" * 60)

    # 8. Close the database connection nicely.
    local_db.close()


if __name__ == "__main__":
    _setup_logging()

    # Check if the user gave us a command-line argument.
    if len(sys.argv) < 2:
        print("Usage: python geocode_uk.py input.csv")
        print("")
        print("  input.csv  -- a CSV file with address columns.")
        print("")
        print("Example columns the script looks for:")
        print("  postcode, street, city")
        sys.exit(1)

    input_file = sys.argv[1]
    main(input_file)
