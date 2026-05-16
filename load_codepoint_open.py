#!/usr/bin/env python3
"""
load_codepoint_open.py
=====================
Why we need this file:
----------------------
Imagine a huge library with 1.8 million books, and each book is a UK postcode.
This script goes to the UK Government's library (Ordnance Survey) and makes a
small, fast personal copy of every book title (postcode) and its location
(latitude and longitude) inside a simple file on YOUR computer.

That file is called 'uk_postcodes.db'. It is a SQLite database.
SQLite is like an Excel sheet that your computer can read instantly without
the internet.

Once we have this local database, looking up a postcode is instant.
No need to ask Google, Bing, or anyone else.
No API keys. No internet needed after this one-time setup.
"""

import csv
import io
import os
import sqlite3
import sys
import zipfile
from pathlib import Path

# We need a tiny helper to turn UK grid numbers (Eastings/Northings)
# into latitude/longitude numbers that maps use everywhere else in the world.
try:
    from OSGridConverter import OSGridReference
except ImportError as exc:
    print(
        "ERROR: The Python package 'osgridconverter' is not installed.\n"
        "It is needed to turn UK grid numbers into regular latitude/longitude.\n"
        "Please install it by running:\n"
        "    uv pip install osgridconverter\n"
        "    OR  pip install osgridconverter\n"
    )
    sys.exit(1)

# --- Settings you can change if you want ---
# DOWNLOAD_URL: Where the UK Government keeps the latest postcode data.
# It is a ZIP file full of CSV files.
DOWNLOAD_URL = (
    "https://api.os.uk/downloads/v1/products/CodePointOpen/downloads?area=GB&format=CSV&redirect"
)

# DATA_DIR: Where we keep our downloaded files and the final database.
# We use a folder called 'data' right next to this script.
SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "data"

# ZIP_PATH: Where we save the downloaded ZIP file.
ZIP_PATH = DATA_DIR / "codepoint_open.zip"

# DB_PATH: The final local database file.
DB_PATH = DATA_DIR / "uk_postcodes.db"


def _make_data_dir():
    """
    Just creates the 'data' folder if it does not already exist.
    Think of it like making sure you have a shoebox before you start sorting shoes.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def download_data():
    """
    This function fetches the big ZIP file from the UK Government website.
    It only downloads if the file is not already on your computer, so you can
    run this script again and again without re-downloading every time.
    """
    if ZIP_PATH.exists():
        print(f"ZIP already exists at {ZIP_PATH}. Skipping download.")
        return

    print(f"Downloading Code-Point Open data from the UK Government...")
    print(f"URL: {DOWNLOAD_URL}")

    try:
        import urllib.request as request
    except ImportError:
        print("ERROR: Your Python installation is missing urllib (this is very unusual).")
        sys.exit(1)

    # We try to download. If the internet is broken, we tell you nicely.
    try:
        request.urlretrieve(DOWNLOAD_URL, ZIP_PATH)
    except Exception as exc:
        print(f"ERROR: Download failed. Reason: {exc}")
        print(
            "\nTip: If the download link is out of date, visit the Ordnance Survey\n"
            "website manually and update DOWNLOAD_URL in this script:\n"
            "    https://osdatahub.os.uk/downloads/open/CodePointOpen\n"
        )
        sys.exit(1)

    print(f"Download complete. Saved to: {ZIP_PATH}")


def build_postcode_database():
    """
    This is the main brain of the script.

    Steps:
    1. Open the ZIP file (no need to unzip it completely; we read inside it).
    2. Walk through every folder and every CSV file inside.
    3. For each row (each postcode), convert the grid numbers to lat/lng.
    4. Save everything into our local 'uk_postcodes.db' SQLite file.

    After this runs, you will have every live UK postcode on your computer
    in under 200 MB, and you can look them up in a millisecond.
    """
    _make_data_dir()
    download_data()

    # If the database already exists, REMOVE the old copy so we start fresh.
    if DB_PATH.exists():
        print(f"Removing old database: {DB_PATH}")
        DB_PATH.unlink()

    print(f"Creating fresh database at: {DB_PATH}")

    # Connect to SQLite. If the file doesn't exist, SQLite invents it.
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create a table to hold the postcodes and coordinates.
    # PRIMARY KEY on 'postcode' makes lookup instant.
    cursor.execute(
        """
        CREATE TABLE postcodes (
            postcode TEXT PRIMARY KEY,
            easting INTEGER,
            northing INTEGER,
            latitude REAL,
            longitude REAL
        )
        """
    )

    # We wrap the whole job in one big transaction so it is lightning fast.
    # Without a transaction, SQLite writes to disk for every single postcode,
    # which would take hours instead of seconds.
    cursor.execute("BEGIN TRANSACTION")

    csv_count = 0
    rows_inserted = 0

    # Open the ZIP and look inside
    with zipfile.ZipFile(ZIP_PATH, "r") as zf:
        for name in zf.namelist():
            # We only care about .csv files.
            # The ZIP contains folders inside folders, so we check the file extension.
            if not name.lower().endswith(".csv"):
                continue

            csv_count += 1
            print(f"  Reading {name} ...")

            # Read the CSV bytes from inside the ZIP.
            with zf.open(name) as csvfile:
                # Decode bytes to text line-by-line, then pass to Python's CSV reader.
                text_stream = io.TextIOWrapper(csvfile, encoding="utf-8", newline="")
                reader = csv.reader(text_stream)

                for row in reader:
                    # The CSV columns for Code-Point Open are:
                    # 0: Postcode            (e.g. 'PL0 1PF')
                    # 1: Positional quality  (a number, we ignore it here)
                    # 2: Eastings            (UK grid X coordinate)
                    # 3: Northings           (UK grid Y coordinate)
                    # 4: Country code        (E/W/S/N/L)
                    # ... and more columns we don't need for simple mapping.
                    if len(row) < 4:
                        continue

                    postcode = row[0].strip().upper()
                    easting_str = row[2].strip()
                    northing_str = row[3].strip()

                    # Skip blank rows
                    if not postcode or not easting_str or not northing_str:
                        continue

                    try:
                        easting = int(easting_str)
                        northing = int(northing_str)
                    except ValueError:
                        # Some rows might have bad data. Just skip them.
                        continue

                    # Convert UK grid numbers to regular world coordinates (latitude/longitude).
                    latlong = OSGridReference(easting, northing).toLatLong()
                    latitude = latlong.latitude
                    longitude = latlong.longitude

                    # Save into the database.
                    cursor.execute(
                        """
                        INSERT INTO postcodes (postcode, easting, northing, latitude, longitude)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (postcode, easting, northing, latitude, longitude),
                    )
                    rows_inserted += 1

    # Save everything to disk and close.
    conn.commit()
    conn.close()

    print(
        f"\nDone!\n"
        f"  CSV files read : {csv_count}\n"
        f"  Postcodes saved: {rows_inserted:,}\n"
        f"  Database file  : {DB_PATH}\n"
        f"  Size on disk   : {DB_PATH.stat().st_size / (1024*1024):.1f} MB\n"
    )


if __name__ == "__main__":
    # "__main__" means 'only run this if I started this file directly'.
    # If this script is imported by another script, it won't run automatically.
    build_postcode_database()
