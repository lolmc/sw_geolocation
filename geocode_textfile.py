#!/usr/bin/env python3
"""
geocode_textfile.py
===================
What is this for?
-----------------
some files are not proper CSV spreadsheets. They are just a plain text list,
with one address per line, like this:

    21 nowhere street, cityville, PL0 1PF
    32 knothere drive, smalltown, XD2 3BP

geocode_uk.py is built for CSV files with column headers.
This script is the same idea, but for plain text files.

It reads each line, tries to extract a postcode at the end,
looks it up locally, and if that fails it asks Nominatim/OpenMapQuest.

Usage:
------
    python geocode_textfile.py gp_sites.txt

Output:
-------
    gc_gp_sites.txt
"""

import csv
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd
from geopy.geocoders import Nominatim, OpenMapQuest
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

import keys
import postcode_utils


SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"
DB_PATH = DATA_DIR / "uk_postcodes.db"
RATE_LIMIT_SECONDS = 1.0
MAX_RETRIES = 3


def _setup_logging():
    logging.basicConfig(
        filename="geocode_log.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    logging.getLogger("").addHandler(console)


class LocalPostcodeDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn = None

    def _connect(self):
        if self._conn is None:
            import sqlite3
            self._conn = sqlite3.connect(self.db_path)
        return self._conn

    def lookup(self, postcode: str) -> Optional[Tuple[float, float]]:
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
        if self._conn:
            self._conn.close()
            self._conn = None


def _extract_postcode(address_line: str) -> Tuple[str, Optional[str]]:
    """
    Try to find a UK postcode hiding at the end of an address line.
    
    UK postcodes are usually the last thing on the line, after the street and city.
    We split by commas and look at the last piece.
    
    Examples:
        '21 nowhere street, cityville, PL0 1PF'   ->  postcode = 'PL0 1PF'
        '32 knothere drive, smalltown, XD2 3BP'   ->  postcode = 'XD2 3BP'
        'Some building in Paris'                    ->  postcode = None
    
    Returns: (clean_address, postcode_or_None)
    """
    parts = [p.strip() for p in address_line.split(",")]
    if not parts:
        return address_line, None

    # Look at the last part. It might be a postcode.
    candidate = parts[-1]
    normalised = postcode_utils.normalise_postcode(candidate)

    if normalised:
        # Remove the postcode from the address so we don't search for it twice.
        clean_parts = parts[:-1]
        clean_address = ", ".join(clean_parts)
        return clean_address, normalised

    return address_line, None


def _init_geocoders():
    geocoders = []
    if getattr(keys, "n_user", None):
        geocoders.append(("nominatim", Nominatim(user_agent=keys.n_user, timeout=10)))
    else:
        geocoders.append(("nominatim", Nominatim(user_agent="sw_geolocation_uk_script", timeout=10)))

    if getattr(keys, "omq_api", None) and keys.omq_api != "YOURUNIQUEAPICODEGOESHERE":
        geocoders.append(("openmapquest", OpenMapQuest(api_key=keys.omq_api, timeout=10)))
    return geocoders


def _internet_geocode(address_text: str, label: str, geocoders: List[Tuple[str, object]]) -> Optional[Tuple[float, float, str]]:
    for source_name, gcoder in geocoders:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                location = gcoder.geocode(address_text)
                if location:
                    logging.info(f"[{label}] SUCCESS via {source_name}: {address_text}")
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
            if attempt < MAX_RETRIES:
                time.sleep(RATE_LIMIT_SECONDS * attempt)
    logging.error(f"[{label}] ALL geocoders failed for: {address_text}")
    return None


def geocode_line(address_line: str, line_number: int, local_db: LocalPostcodeDB, geocoders: List[Tuple[str, object]]) -> dict:
    """
    Geocode a single line from a plain text file.
    Returns a flat dictionary ready to be saved in a table.
    """
    original = address_line.strip()
    if not original:
        return {
            "original_address": original,
            "lat": None,
            "lng": None,
            "postcode": None,
            "geocode_source": "blank_line",
            "geocode_date": datetime.utcnow().isoformat(),
        }

    clean_address, postcode = _extract_postcode(original)

    # --- Try local DB first ---
    if postcode:
        local_result = local_db.lookup(postcode)
        if local_result:
            lat, lng = local_result
            logging.info(f"[line {line_number}] FOUND in local DB: {postcode} -> {lat}, {lng}")
            return {
                "original_address": original,
                "lat": lat,
                "lng": lng,
                "postcode": postcode,
                "geocode_source": "codepoint_open",
                "geocode_date": datetime.utcnow().isoformat(),
            }

    # --- Internet fallback ---
    result = _internet_geocode(clean_address, f"line {line_number}", geocoders)
    if result:
        lat, lng, source = result
        logging.info(f"[line {line_number}] FOUND via internet: {clean_address}")
        return {
            "original_address": original,
            "lat": lat,
            "lng": lng,
            "postcode": postcode,
            "geocode_source": source,
            "geocode_date": datetime.utcnow().isoformat(),
        }

    logging.error(f"[line {line_number}] FAILED: {original}")
    return {
        "original_address": original,
        "lat": None,
        "lng": None,
        "postcode": postcode,
        "geocode_source": "failed",
        "geocode_date": datetime.utcnow().isoformat(),
    }


def main(input_file: str):
    input_path = Path(input_file)
    output_path = input_path.parent / f"gc_{input_path.name}"

    logging.info("=" * 60)
    logging.info("Starting geocode_textfile.py")
    logging.info(f"Input file : {input_path}")
    logging.info(f"Output file: {output_path}")

    if not input_path.exists():
        logging.error(f"Input file not found: {input_path}")
        print(f"ERROR: Could not find input file: {input_path}")
        sys.exit(1)

    print(f"Reading text file: {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    print(f"Loaded {len(lines)} lines.")

    local_db = LocalPostcodeDB(DB_PATH)
    if not DB_PATH.exists():
        print(
            "\nWARNING: Local postcode database not found.\n"
            "         Run 'python load_codepoint_open.py' first.\n"
            "         Falling back to internet-only geocoding.\n"
        )
        logging.warning("Local postcode DB not found. Using internet fallback only.")

    geocoders = _init_geocoders()
    if not geocoders:
        print("WARNING: No internet geocoders configured.")
        logging.warning("No internet geocoders configured.")

    print("Geocoding lines...")
    results = []
    for i, line in enumerate(lines, start=1):
        result = geocode_line(line, i, local_db, geocoders)
        results.append(result)

    df = pd.DataFrame(results)
    df.to_csv(output_path, encoding="utf-8", index=False)
    print(f"Done! Results saved to: {output_path}")
    logging.info(f"Finished. Total lines: {len(df)}. Output: {output_path}")
    logging.info("=" * 60)
    local_db.close()


if __name__ == "__main__":
    _setup_logging()
    if len(sys.argv) < 2:
        print("Usage: python geocode_textfile.py addresses.txt")
        print("")
        print("  geocodes a plain text file with one address per line.")
        sys.exit(1)
    main(sys.argv[1])
