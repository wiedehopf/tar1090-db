#!/bin/bash
set -e
function compress() {
    rm -f "$1.gz"
    7za a -mx=9 "$1.gz" "$1"
}
rm aircraft.csv.gz
git checkout csv
compress aircraft.csv
if [[ -f /usr/local/share/tar1090/aircraft.csv.gz ]]; then
    cp aircraft.csv.gz /usr/local/share/tar1090/aircraft.csv.gz
fi
git add aircraft.csv.gz

VERSION="3.14.$(( $(cat version | cut -d'.' -f3) + 1 ))"
echo "$VERSION" > version
git add version

git commit --amend --date "$(date)" -m "aircraft.csv.gz update"
git push -f
git checkout master
