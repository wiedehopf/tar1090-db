#!/bin/bash

# tar1090-db only has a lookup table of IATA / ICAO codes, no other airport info
# uses data from https://ourairports.com/data/

wget https://davidmegginson.github.io/ourairports-data/airports.csv -O ourairports.csv

python3 ap.py
