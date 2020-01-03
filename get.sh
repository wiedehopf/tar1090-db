#!/bin/bash
set -e
wget -O newTypes.json --compression=auto https://raw.githubusercontent.com/Mictronics/readsb-protobuf/dev/webapp/src/db/types.json &
wget -O mic-db.zip https://www.mictronics.de/aircraft-database/indexedDB_old.php
unzip -o mic-db.zip

wget -O basic-ac-db.json.gz http://downloads.adsbexchange.com/downloads/basic-ac-db.json.gz
rm -f basic-ac-db.json
gunzip -k basic-ac-db.json.gz
sed -i basic-ac-db.json \
    -e 's#\\\\.##g' \
    -e 's#\\.##g' \
    -e 's#\\##g'

function compress() {
    rm -f "$1.gz"
    7za a -mx=9 "$1.gz" "$1"
}

rm -f db/*
cp ranges.json db/ranges.js
cp airport-coords.json db/airport-coords.js
cp types.json db/icao_aircraft_types.js
cp operators.json db/operators.js


sed -i -e 's/},/},\n/g' aircrafts.json
sed -e 's#\\u00c9#\xc3\x89#g' \
    -e 's#\\u00e9#\xc3\xa9#g' \
    -e 's#\\/#/#g' \
    -e "s/''/'/g" \
    aircrafts.json > aircraftUtf.json

perl -i -pe 's/\\u00(..)/chr(hex($1))/eg' aircraftUtf.json

./toJson.py aircraftUtf.json db newTypes.json basic-ac-db.json

for file in db/*; do
    compress "$file"
    mv "$file.gz" "$file"
done
git add db

sed -i -e 's/\\;/,/' aircraft.csv
compress aircraft.csv
git add aircraft.csv.gz
