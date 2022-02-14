#!/bin/bash
set -e

function getGIT() {
    # getGIT $REPO $BRANCH $TARGET (directory)
    if [[ -z "$1" ]] || [[ -z "$2" ]] || [[ -z "$3" ]]; then echo "getGIT wrong usage, check your script or tell the author!" 1>&2; return 1; fi
    REPO="$1"; BRANCH="$2"; TARGET="$3"; pushd .
    if cd "$TARGET" &>/dev/null && git fetch --depth 1 origin "$BRANCH" && git reset --hard FETCH_HEAD; then popd; return 0; fi
    if ! cd /tmp || ! rm -rf "$TARGET"; then popd; return 1; fi
    if git clone --depth 1 --single-branch --branch "$2" "$1" "$3"; then popd; return 0; fi
    popd; return 1;
}

getGIT https://github.com/chrisglobe/adsbx-type-longnames-chrisglobe.git main "$(pwd)/longnames"

wget -O newTypes.json --compression=auto https://raw.githubusercontent.com/Mictronics/readsb-protobuf/dev/webapp/src/db/types.json
wget -O mic-db.zip https://www.mictronics.de/aircraft-database/indexedDB_old.php
unzip -o mic-db.zip

wget -O basic-ac-db.json.gz https://downloads.adsbexchange.com/downloads/basic-ac-db.json.gz
gunzip -c basic-ac-db.json.gz > basic-ac-db.json
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
cp newTypes.json db/icao_aircraft_types2.js
cp operators.json db/operators.js


sed -i -e 's/},/},\n/g' aircrafts.json
sed -e 's#\\u00c9#\xc3\x89#g' \
    -e 's#\\u00e9#\xc3\xa9#g' \
    -e 's#\\/#/#g' \
    -e "s/''/'/g" \
    aircrafts.json > aircraftUtf.json

perl -i -pe 's/\\u00(..)/chr(hex($1))/eg' aircraftUtf.json

./toJson.py aircraftUtf.json db newTypes.json basic-ac-db.json

sed -i -e 's/\\;/,/' aircraft.csv

for file in db/*; do
    compress "$file"
    mv "$file.gz" "$file"
done

git add db
git commit --amend --date "$(date)" -m "database update (to keep the repository small, this commit is replaced regularly)"
git push -f
