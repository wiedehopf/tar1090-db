#!/bin/bash
set -e
wget --compression=auto -O aircraft.json https://raw.githubusercontent.com/Mictronics/readsb-protobuf/dev/webapp/src/db/aircrafts.json

function compress() {
    7za a -mx=9 "$1.gz" "$1"
}

rm -f db/*
cp airport-coords.json db/airport-coords.js
cp icao_aircraft_types.json db/icao_aircraft_types.js

sed -i -e 's/},/},\n/g' aircraft.json
sed -e 's#\\u00c9#\xc3\x89#g' \
    -e 's#\\u00e9#\xc3\xa9#g' \
    -e 's#\\/#/#g' \
    -e "s/''/'/g" \
    aircraft.json > aircraftUtf.json

perl -i -pe 's/\\u00(..)/chr(hex($1))/eg' aircraftUtf.json

./toJson.py aircraftUtf.json db

for file in db/*; do
    compress "$file"
    mv "$file.gz" "$file"
done
git add db

sed -i -e 's/\\;/,/' aircraft.csv
compress aircraft.csv
git add aircraft.csv.gz
