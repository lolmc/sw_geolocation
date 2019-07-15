# sw_geolocation
Solarwinds geolocation data creation

This Python script utilizes the GeoPy geocoding library to batch geocode a number of addresses, using various services
until a pair of latitude/longitude values are returned. Python 3 port and refactor of a script by @rgdonohue.
https://gist.github.com/ericmhuntley/0c293113aa75a254237c143e0cf962fa
Built to anticipate an input csv should that includes columns named street, city, state, country.
Usage Example
python geocode.py data.csv 100
Where data.csv is an appropriately formatted csv encoded in utf-8 and 100 is the timout between each request in units of
milliseconds.

A number of geolocation APIs can be polled for an answer but I have only tested it using the Open map Quest API as it was the easiest to set up and free!

I have added a logger function to take note of when things go wrong so feel free to turn that off if you want.
