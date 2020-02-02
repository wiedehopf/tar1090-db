set -e
wget --compression=auto -O aircraft.json https://raw.githubusercontent.com/Mictronics/readsb/master/webapp/src/db/aircrafts.json

rm -f db/*
cp airport-coords.json icao_aircraft_types.json db
gzip -9 -k db/*.json -f
./toJson.py aircraft.json db
