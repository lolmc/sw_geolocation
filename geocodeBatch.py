'''
Multi-Service Geocoder

This Python script utilizes the GeoPy geocoding library to batch geocode a number of addresses, using various services
until a pair of latitude/longitude values are returned. Python 3 port and refactor of a script by @rgdonohue.
https://gist.github.com/ericmhuntley/0c293113aa75a254237c143e0cf962fa
Built to anticipate an input csv should that includes columns named street, city, state, country.
Usage Example
python geocode.py data.csv 100
Where data.csv is an appropriately formatted csv encoded in utf-8 and 100 is the timout between each request in units of
milliseconds.
'''
# import the geocoding services you'd like to try
from geopy.geocoders import ArcGIS, Bing, Nominatim, OpenCage, GoogleV3, OpenMapQuest
import csv, sys
import pandas as pd
import keys
import logging

logging.basicConfig(
    filename="geocode_log.log",
    level=logging.DEBUG,
    format="%(asctime)s:%(levelname)s:%(message)s"
    )
in_file = 'gp_sites.txt'
out_file = str('gc_' + in_file)
timeout = 100

print('creating geocoding objects.')
logging.debug('creating geocoding objects.')
openmapquest = OpenMapQuest(api_key=keys.omq_api, timeout=timeout)

# choose and order your preference for geocoders here
geocoders = [openmapquest]

def gc(address):
    for gcoder in geocoders:
        location = gcoder.geocode(address)
        if location != None:
            #print(f'geocoded record {address}')
            #logging.info(f'SUCCESSFULLY geocoded record {address}')
            located = pd.Series({
                'lat': location.latitude,
                'lng': location.longitude,
                'time': pd.to_datetime('now')
            })
        else:
            #print(f'failed to geolocate record {address}')
            logging.debug(f'FAILED to geolocate record {address}')
            located = pd.Series({
                'lat': 'null',
                'lng': 'null',
                'time': pd.to_datetime('now')
            })
        return located

print('opening input.')
f = open(in_file, "r")
print('geocoding addresses.')
reader = ''
for address in f:
    #print(address)
    reader = gc(address)
print(f'writing to {out_file}.csv')
reader.to_csv(out_file, encoding='utf-8', index=False)
print('done.')