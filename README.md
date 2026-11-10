# tar1090-db
Database repo for tar1090 using the database maintained by Mictronics (https://www.mictronics.de/aircraft-database/)

## Current Update Process

```bash
./update.sh
```

### Download link for the current aircraft.csv.gz

<https://github.com/wiedehopf/tar1090-db/raw/refs/heads/csv/aircraft.csv.gz>

### Update aircraft.csv.gz for readsb server version

```bash
./csv.sh
```

---

## EWS (Early Warning System) & SQLite Query Utility

For downstream applications, radar monitoring daemons, and Early Warning Systems (EWS) that need single-file SQL querying or fast Mode-S military / threat profile classification outside the web browser context (resolving Issue #19):

### Build SQLite Database

Generate an indexed SQLite database (`aircraft.sqlite`) with WAL mode from `aircraft.csv` (or `aircraft.csv.gz`) and `ranges.json`:

```bash
python3 ews.py --build --csv aircraft.csv --ranges ranges.json --db aircraft.sqlite
```

### Fast CLI Lookups & Category Filtering

```bash
# Lookup Mode-S 24-bit hex:
python3 ews.py --lookup 4B8201

# Filter by EWS operational category (e.g. MIL_AEW_C, MIL_FIGHTER, MIL_RECON_ISR, STATE_VIP):
python3 ews.py --query-category MIL_AEW_C --limit 10

# Database statistics:
python3 ews.py --stats
```

### Python API

```python
import ews

# Instant Mode-S military interval check
matcher = ews.MilitaryRangeMatcher.from_ranges_json("ranges.json")
is_mil = matcher.is_military("ADF7C8")  # True

# Country allocation resolution (ICAO Annex 10)
country_code, country_name = ews.resolve_country("4B8201")  # ("TR", "Turkey")

# Query SQLite database
client = ews.EWSClient("aircraft.sqlite")
aircraft = client.lookup("ADF7C9")
client.close()
```

---

## Testing

Run the test suite across supported Python versions:

```bash
python3 -m unittest discover -s tests -v
```
