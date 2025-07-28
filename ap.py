import json, re, csv
with open("ourairports.csv") as f:
    reader = csv.DictReader(f)
    table = list(reader)

#print(json.dumps(table[39332]))
# expected format:
# "id": "3622",
# "ident": "KJFK",
# "type": "large_airport",
# "name": "John F Kennedy International Airport",
# "latitude_deg": "40.639447",
# "longitude_deg": "-73.779317",
# "elevation_ft": "13",
# "continent": "NA",
# "iso_country": "US",
# "iso_region": "US-NY",
# "municipality": "New York",
# "scheduled_service": "yes",
# "icao_code": "KJFK",
# "iata_code": "JFK",
# "gps_code": "KJFK",
# "local_code": "JFK",
# "home_link": "https://www.jfkairport.com/",
# "wikipedia_link": "https://en.wikipedia.org/wiki/John_F._Kennedy_International_Airport",
# "keywords": "Manhattan, New York City, NYC, Idlewild, IDL, KIDL"

# we make a lookup table using icao and iata codes as the key
# iata codes will take precedence
lookup = {}

for a in table:
    if a.get('icao_code') and a.get('latitude_deg'):
        dupe = 0
        icao = a['icao_code']
        lat = a.get('latitude_deg')
        lon = a.get('longitude_deg')
        if re.search(r'\d', icao, 0):
            # ignore all icao codes with numbers in them to keep filesize down
            # it's generally very small airports
            continue

        # print(f"{icao} {lat} {lon}")

        if icao in lookup:
            if not 'faa_lid' in a:
                print(f"ignoring {a.get('name')} with type {a.get('type')}")
                continue
            else:
                old = lookup[icao]
                print(f"old:       {old.get('name')} with type {old.get('type')}")
                print(f"overwrite: {a.get('name')} with type {a.get('type')}")

        lookup[icao] = a

for a in table:
    if a.get('iata_code') and a.get('latitude_deg'):
        dupe = 0
        iata = a['iata_code']
        lat = a.get('latitude_deg')
        lon = a.get('longitude_deg')
        if re.search(r'\d', icao, 0):
            # ignore all icao codes with numbers in them to keep filesize down
            # it's generally very small airports
            continue

        # print(f"{iata} {lat} {lon}")

        if iata in lookup:
            old = lookup[iata]
            print(f"iata old:       {old.get('name')} with type {old.get('type')}")
            print(f"iata overwrite: {a.get('name')} with type {a.get('type')}")

        lookup[iata] = a


# the output to the json file will only have the coordinates truncated to 4 decimal digits
# 3 decimal digits would probably be fine but 4 doesn't hurt

out = {}
for key, value in lookup.items():
    out[key] = [
            round(float(value.get('latitude_deg')), 4),
            round(float(value.get('longitude_deg')), 4)
            ]
    # print(f"{key} {out[key]}")


with open('airport-coords.json', 'w') as outFile:
    json.dump(out, outFile, separators=(',', ':'))

