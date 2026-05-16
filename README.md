sw_geolocation
==============
Batch geocoding for UK postcodes using free Ordnance Survey data.
Designed to feed lat/lng coordinates into SolarWinds World Map.

Quick Start
-----------

1. Install dependencies:
    pip install osgridconverter geopy pandas

2. Build the local postcode database (~200 MB, one-time):
    python load_codepoint_open.py

3. Geocode a CSV:
    python geocode_uk.py data.csv

Or a plain text file:
    python geocode_textfile.py gp_sites.txt

4. Validate the results:
    python validate_coordinates.py gc_data.csv

5. Load gc_data.csv into SolarWinds dbo.StagingGeocodes, then run
   Update_WorldMapPoints_From_Staging.sql to sync the map.

That's it. UK postcodes need no API keys and no internet after step 2.


Why This Exists
---------------

The old approach (geocode.py, geocodeBatch.py) asked OpenMapQuest for
every address. That meant API keys, rate limits, network dependency, and
quiet costs for large lists.

The new approach keeps a local copy of every UK postcode (Code-Point Open)
and looks them up instantly. Internet geocoders are used only as a fallback
for non-UK addresses or missing postcodes.


File Guide
----------

postcode_utils.py
    Helper that normalises messy postcodes (e.g. "pl01pf" -> "PL0 1PF").
    Imported by other scripts. Not run directly.

load_codepoint_open.py
    Downloads the latest Code-Point Open ZIP from Ordnance Survey and
    builds data/uk_postcodes.db. Run once, or quarterly for fresh data.

geocode_uk.py
    Main script for CSV input. Accepts columns: postcode, post code,
    postalCode, street, city. Outputs gc_<input>.csv with lat, lng,
    geocode_source, geocode_date columns.

geocode_textfile.py
    Same logic for plain text files (one address per line).
    Extracts the postcode automatically.

validate_coordinates.py
    Sanity-checks that lat/lng values fall inside the UK bounding box.
    Writes a flagged_<input>.csv of suspicious rows.

Update_WorldMapPoints_From_Staging.sql
    Replaces the old hardcoded SQL. Creates dbo.StagingGeocodes and a
    MERGE into WorldMapPoints. Add new sites by adding rows to the CSV,
    not by editing CASE/THEN blocks.

keys.py
    Settings file. For UK-only lookups you can leave this blank.
    Only needed if you want Nominatim/OpenMapQuest fallbacks for non-UK
    addresses. Set n_user to your email for Nominatim politeness.


Input / Output
--------------

Input CSV columns the geocode_uk.py recognises:
    postcode, post code, postalCode, postal_code, PostCode
    street (optional)
    city   (optional)

Output CSV adds:
    lat              -- latitude
    lng              -- longitude
    geocode_source   -- where the value came from
                       codepoint_open = local DB (best)
                       nominatim      = OpenStreetMap (fallback)
                       openmapquest   = MapQuest (fallback)
                       failed         = no result
    geocode_date     -- ISO timestamp of the lookup


SQL / SolarWinds
----------------

The new SQL script removes every hardcoded lat/lng from the old file.
Instead:

1. Load the geocoded CSV into dbo.StagingGeocodes (BULK INSERT or SSMS).
2. Run the MERGE statement in Update_WorldMapPoints_From_Staging.sql.

The MERGE handles insert, update, and delete automatically. New sites
appear on the map, moved sites update, and removed sites disappear.


Troubleshooting
---------------

Local database not found?
    Run load_codepoint_open.py first.

UK postcode returns nothing?
    Check spelling. Postcodes change occasionally; the data is refreshed
    quarterly by Ordnance Survey.

Non-UK address fails?
    Set n_user in keys.py. Nominatim requires a user agent.

Results look wrong?
    Run validate_coordinates.py. It flags coordinates outside the UK and
    blank results.


Dependencies
------------

Python 3.8+
    pip install osgridconverter geopy pandas

The osgridconverter package converts OS grid references (easting/northing)
to latitude/longitude during the initial database build.


Licence / Data Source
---------------------

Code-Point Open Data (c) Crown copyright and database rights 2025
Ordnance Survey (OS), 100025252
https://osdatahub.os.uk/downloads/open/CodePointOpen

Scripts build on GeoPy and ideas from @rgdonohue.


Changelog
---------
v2.0  Tiered geocoding: local Code-Point DB first, internet fallback second.
      Added postcode normalisation, result validation, and staging-table SQL.
v1.0  Original GeoPy + OpenMapQuest batch script.
