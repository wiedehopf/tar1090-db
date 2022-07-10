import json, re
ap = {}
with open("airports.json") as jsonFile:
    ap = json.load(jsonFile)

out = {}


table = ap['airports']

for a in table:
    if 'icao_code' in a and 'coordinates' in a:
        dupe = 0
        icao = a['icao_code']
        if not re.search(r'\d', icao, 0):
            if icao in out:
                print(icao)
                print(out[icao])
                dupe = 1
                if not 'faa_lid' in a:
                    continue

            out[icao] = [a['coordinates']['latitude'], a['coordinates']['longitude']]

            if dupe == 1:
                print(out[icao])
    if 'iata_code' in a and 'coordinates' in a:
        iata = a['iata_code']
        out[iata] = [a['coordinates']['latitude'], a['coordinates']['longitude']]


with open('lookup.json', 'w') as outFile:
        json.dump(out, outFile)

