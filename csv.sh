#!/bin/bash
set -e
function compress() {
    rm -f "$1.gz"
    7za a -mx=9 "$1.gz" "$1"
}
rm -f aircraft.csv.gz
git checkout csv
compress aircraft.csv
if [[ -f /usr/local/share/tar1090/aircraft.csv.gz ]]; then
    cp aircraft.csv.gz /usr/local/share/tar1090/aircraft.csv.gz
fi
git add aircraft.csv.gz
git commit --amend --date "$(date)" -m "aircraft.csv.gz update"
git push -f
git checkout master
