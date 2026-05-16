#!/usr/bin/env python3
"""
validate_coordinates.py
=========================
What is this for?
-----------------
Sometimes geocoders make mistakes. Like a SAT NAV sending you into a river.
This script reads a file that already has lat/lng coordinates,
and checks whether each coordinate makes sense.

It checks TWO things:
1. Is the coordinate actually inside the United Kingdom?
   (Because most of the addresses we care about SHOULD be in the UK.)
2. Are there any rows where the geocoding completely failed
   (lat/lng are blank or zero)?

If a coordinate looks suspicious, this script prints a WARNING so you know
which rows to check by hand.

Usage:
------
    python validate_coordinates.py gc_data.csv

    Output: A short report in the terminal + optional flag file
"""

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd


# --- Settings ---
# These are rough edges of the United Kingdom bounding box.
# If a pin falls outside this box, it is probably wrong.
# (The box includes a little sea around the edges, so it is forgiving.)
UK_LAT_MIN, UK_LAT_MAX = 49.8, 60.8
UK_LNG_MIN, UK_LNG_MAX = -8.6, 1.8


def _is_uk(lat: float, lng: float) -> bool:
    """True if the lat/lng is inside the rough UK box."""
    return UK_LAT_MIN <= lat <= UK_LAT_MAX and UK_LNG_MIN <= lng <= UK_LNG_MAX


def validate_csv(csv_path: str) -> Tuple[int, int, int, List[dict]]:
    """
    Reads the CSV and counts:
    - total_rows     : how many rows in total
    - failed_rows    : rows with no coordinates at all
    - suspicious_rows: rows with coordinates that look outside the UK
    - details        : a list of every suspicious/failed row for printing

    Returns a report summary that the main() function can print nicely.
    """
    path = Path(csv_path)
    if not path.exists():
        print(f"ERROR: File not found: {path}")
        sys.exit(1)

    df = pd.read_csv(csv_path, dtype=str)

    total_rows = len(df)
    failed_rows = 0
    suspicious_rows = 0
    details = []

    for idx, row in df.iterrows():
        # Try to read lat and lng as numbers.
        lat_str = row.get("lat", "").strip() if pd.notna(row.get("lat")) else ""
        lng_str = row.get("lng", "").strip() if pd.notna(row.get("lng")) else ""

        # --- Check for completely missing data ---
        if not lat_str or lat_str.lower() in ("nan", "null", "none", ""):
            failed_rows += 1
            details.append(
                {
                    "row": idx + 2,  # +2 because Excel row 1 is headers.
                    "issue": "NO COORDINATES",
                    "lat": row.get("lat"),
                    "lng": row.get("lng"),
                    "postcode": row.get("postcode", row.get("post code", row.get("postalCode", ""))),
                    "reason": "lat/lng are blank -- geocoding failed",
                }
            )
            continue

        try:
            lat = float(lat_str)
            lng = float(lng_str)
        except (ValueError, TypeError):
            failed_rows += 1
            details.append(
                {
                    "row": idx + 2,
                    "issue": "BAD VALUE",
                    "lat": lat_str,
                    "lng": lng_str,
                    "postcode": row.get("postcode", row.get("post code", row.get("postalCode", ""))),
                    "reason": "lat/lng are not numbers",
                }
            )
            continue

        # --- Check for suspicious coordinates (outside UK) ---
        if not _is_uk(lat, lng):
            suspicious_rows += 1
            details.append(
                {
                    "row": idx + 2,
                    "issue": "OUTSIDE UK",
                    "lat": lat,
                    "lng": lng,
                    "postcode": row.get("postcode", row.get("post code", row.get("postalCode", ""))),
                    "reason": f"lat/lng {lat},{lng} falls outside UK bounding box",
                    "geocode_source": row.get("geocode_source", "unknown"),
                }
            )

    return total_rows, failed_rows, suspicious_rows, details


def main(csv_path: str):
    """
    The conductor. It calls validate_csv to do the work,
    then prints a nice report card.
    """
    print(f"Validating coordinates in: {csv_path}\n")

    total, failed, suspicious, details = validate_csv(csv_path)

    ok_rows = total - failed - suspicious

    print("=" * 60)
    print("VALIDATION REPORT")
    print("=" * 60)
    print(f"Total rows checked : {total}")
    print(f"Looks good (ok)    : {ok_rows}")
    print(f"Failed (no coords) : {failed}")
    print(f"Suspicious (wrong area) : {suspicious}")
    print(f"Success rate       : {(ok_rows / total * 100) if total > 0 else 0:.1f}%")
    print("=" * 60)

    if details:
        print("\nDETAILS (rows that need attention):")
        print("-" * 60)
        for d in details:
            print(
                f"  Row {d['row']:4} | {d['issue']:12} | "
                f"lat={d['lat']}, lng={d['lng']} | {d['reason']}"
            )
        print("-" * 60)
        print(
            "\nTip: Look up these rows by hand. The postcode might be wrong,\n"
            "     or the geocoder might have guessed the wrong country.\n"
        )
        # Save a CSV of the flagged rows so you can open it in Excel.
        flagged_path = Path(csv_path).parent / f"flagged_{Path(csv_path).name}"
        flagged_df = pd.DataFrame(details)
        flagged_df.to_csv(flagged_path, index=False)
        print(f"Flagged rows saved to: {flagged_path}")
    else:
        print("\nAll coordinates look good! No action needed.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_coordinates.py gc_data.csv")
        print("")
        print("  Checks that lat/lng coordinates in the file actually look like UK coordinates.")
        sys.exit(1)

    main(sys.argv[1])
