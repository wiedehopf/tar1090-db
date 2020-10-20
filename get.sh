set -e
wget --compression=auto -O aircraft.json https://raw.githubusercontent.com/Mictronics/readsb-protobuf/dev/webapp/src/db/aircrafts.json

rm -f db/*
cp airport-coords.json db/airport-coords.js
cp icao_aircraft_types.json db/icao_aircraft_types.js
./toJson.py aircraft.json db
sed -i -e 's/\\;/,/' aircraft.csv
git add db
gzip -9 aircraft.csv
git add aircraft.csv.gz
