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
in_file = 'data.csv'
out_file = str('gc_' + in_file)
timeout = 100

print('creating geocoding objects.')
logging.debug('creating geocoding objects.')
#arcgis = ArcGIS(timeout=timeout)
#bing = Bing(api_key=keys.bing_api,timeout=100)
#nominatim = Nominatim(user_agent=keys.n_user, timeout=timeout)
#opencage = OpenCage(api_key=keys.oc_api,timeout=timeout)
#googlev3 = GoogleV3(api_key=keys.g3_api, domain='maps.googleapis.com', timeout=timeout)
openmapquest = OpenMapQuest(api_key=keys.omq_api, timeout=timeout)

# choose and order your preference for geocoders here
geocoders = [openmapquest]

def gc(address):
    street = str(address['street'])
    city = str(address['city'])
    postalCode = str(address['postalCode'])
    add_concat = street + ", " + city + ", " + postalCode
    for gcoder in geocoders:
        location = gcoder.geocode(add_concat)
        if location != None:
            print(f'geocoded record {address.name}: {street}')
            logging.info(f'SUCCESSFULLY geocoded record {address}')
            located = pd.Series({
                'lat': location.latitude,
                'lng': location.longitude,
                #'time': pd.to_datetime('now')
            })
        else:
            print(f'failed to geolocate record {address.name}: {street}')
            logging.debug(f'FAILED to geolocate record {address}')
            located = pd.Series({
                'lat': 'null',
                'lng': 'null',
                'time': pd.to_datetime('now')
            })
        return located

print('opening input.')
reader = pd.read_csv(in_file, header=0)
print('csv data:', reader)
print('geocoding addresses.')
reader = reader.merge(reader.apply(lambda add: gc(add), axis=1), left_index=True, right_index=True)
print(f'writing to {out_file}.')
reader.to_csv(out_file, encoding='utf-8', index=False)
print('done.')