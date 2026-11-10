#!/usr/bin/env python3
"""
EWS (Early Warning System) & ADS-B Aircraft Database Infrastructure
for tar1090-db / readsb.

Features:
- Fast Mode-S 24-bit military range lookup using interval binary search.
- ICAO Annex 10 country / state authority delegation resolution.
- EWS threat & mission profile classification (Fighter, AEW&C / AWACS, Recon/ISR,
  Tanker, Military Transport, Rotorcraft, State VIP, Emergency / SAR).
- SQLite database generation from aircraft.csv with covering indices, WAL mode,
  and sub-millisecond query performance (resolves Issue #19).
- Clean CLI and importable Python API for downstream EWS / radar daemon integration.
"""

import sys
import os
import json
import csv
import gzip
import sqlite3
import bisect
import argparse
from typing import Dict, List, Optional, Tuple, Any

# ==============================================================================
# 1. ICAO 24-bit Mode S National Address Allocation (ICAO Annex 10 Vol III Ch 9)
# ==============================================================================

# List of (start_int, end_int, country_code, country_name)
ICAO_COUNTRY_BLOCKS = [
    (0x004000, 0x0043FF, "ZW", "Zimbabwe"),
    (0x008000, 0x00FFFF, "MZ", "Mozambique"),
    (0x010000, 0x017FFF, "ZA", "South Africa"),
    (0x020000, 0x027FFF, "NG", "Nigeria"),
    (0x068000, 0x06FFFF, "EG", "Egypt"),
    (0x080000, 0x087FFF, "DZ", "Algeria"),
    (0x100000, 0x1FFFFF, "RU", "Russian Federation"),
    (0x380000, 0x3BFFFF, "FR", "France"),
    (0x3C0000, 0x3FFFFF, "DE", "Germany"),
    (0x400000, 0x43FFFF, "GB", "United Kingdom"),
    (0x440000, 0x447FFF, "AT", "Austria"),
    (0x448000, 0x44FFFF, "BE", "Belgium"),
    (0x458000, 0x45FFFF, "DK", "Denmark"),
    (0x460000, 0x467FFF, "FI", "Finland"),
    (0x468000, 0x46FFFF, "GR", "Greece"),
    (0x470000, 0x477FFF, "IT", "Italy"),
    (0x480000, 0x487FFF, "NL", "Netherlands"),
    (0x488000, 0x48FFFF, "NO", "Norway"),
    (0x490000, 0x497FFF, "PL", "Poland"),
    (0x498000, 0x49FFFF, "PT", "Portugal"),
    (0x4A0000, 0x4A7FFF, "RO", "Romania"),
    (0x4A8000, 0x4AFFFF, "SE", "Sweden"),
    (0x4B0000, 0x4B7FFF, "CH", "Switzerland"),
    (0x4B8000, 0x4BFFFF, "TR", "Turkey"),
    (0x4C8000, 0x4CFFFF, "CY", "Cyprus"),
    (0x500000, 0x507FFF, "UA", "Ukraine"),
    (0x508000, 0x50FFFF, "KZ", "Kazakhstan"),
    (0x700000, 0x707FFF, "AF", "Afghanistan"),
    (0x708000, 0x70FFFF, "SA", "Saudi Arabia"),
    (0x710000, 0x717FFF, "KR", "Republic of Korea"),
    (0x720000, 0x727FFF, "IQ", "Iraq"),
    (0x730000, 0x737FFF, "IL", "Israel"),
    (0x738000, 0x73FFFF, "JO", "Jordan"),
    (0x740000, 0x747FFF, "LB", "Lebanon"),
    (0x748000, 0x74FFFF, "MY", "Malaysia"),
    (0x750000, 0x757FFF, "PH", "Philippines"),
    (0x758000, 0x75FFFF, "PK", "Pakistan"),
    (0x760000, 0x767FFF, "SG", "Singapore"),
    (0x768000, 0x76FFFF, "LK", "Sri Lanka"),
    (0x770000, 0x777FFF, "SY", "Syrian Arab Republic"),
    (0x780000, 0x7BFFFF, "CN", "China"),
    (0x7C0000, 0x7FFFFF, "AU", "Australia"),
    (0x800000, 0x83FFFF, "IN", "India"),
    (0x840000, 0x87FFFF, "JP", "Japan"),
    (0x880000, 0x887FFF, "TH", "Thailand"),
    (0x890000, 0x897FFF, "ID", "Indonesia"),
    (0x900000, 0x907FFF, "AZ", "Azerbaijan"),
    (0xA00000, 0xAFFFFF, "US", "United States"),
    (0xC00000, 0xC3FFFF, "CA", "Canada"),
    (0xE00000, 0xE3FFFF, "AR", "Argentina"),
    (0xE40000, 0xE7FFFF, "BR", "Brazil"),
    (0xE80000, 0xE87FFF, "CL", "Chile"),
]

# Sort country blocks by start address for binary search
ICAO_COUNTRY_BLOCKS.sort(key=lambda x: x[0])
_COUNTRY_STARTS = [x[0] for x in ICAO_COUNTRY_BLOCKS]


def resolve_country(icao_hex: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve ISO country code and country name from 24-bit Mode-S ICAO hex.
    Returns (code, name) or (None, None).
    """
    try:
        val = int(icao_hex, 16)
    except (ValueError, TypeError):
        return None, None

    idx = bisect.bisect_right(_COUNTRY_STARTS, val) - 1
    if idx >= 0:
        start, end, code, name = ICAO_COUNTRY_BLOCKS[idx]
        if start <= val <= end:
            return code, name
    return None, None


# ==============================================================================
# 2. Military Ranges Loader & Binary Search Interval Checker
# ==============================================================================

class MilitaryRangeMatcher:
    """Fast binary search matcher for ICAO Mode S military allocation ranges."""

    def __init__(self, ranges: Optional[List[Tuple[int, int]]] = None):
        self.ranges: List[Tuple[int, int]] = []
        if ranges:
            self._set_ranges(ranges)

    def _set_ranges(self, raw_ranges: List[Tuple[int, int]]):
        if not raw_ranges:
            self.ranges = []
            self.starts = []
            return

        # Sort and merge overlapping / adjacent intervals
        sorted_ranges = sorted(raw_ranges, key=lambda x: x[0])
        merged = [sorted_ranges[0]]
        for cur_start, cur_end in sorted_ranges[1:]:
            prev_start, prev_end = merged[-1]
            if cur_start <= prev_end + 1:
                merged[-1] = (prev_start, max(prev_end, cur_end))
            else:
                merged.append((cur_start, cur_end))

        self.ranges = merged
        self.starts = [r[0] for r in self.ranges]

    @classmethod
    def from_ranges_json(cls, path: str) -> "MilitaryRangeMatcher":
        """Load from tar1090-db ranges.json file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_ranges = []
        for item in data.get("military", []):
            if len(item) >= 2:
                try:
                    s = int(item[0], 16)
                    e = int(item[1], 16)
                    raw_ranges.append((s, e))
                except ValueError:
                    continue
        return cls(raw_ranges)

    def is_military(self, icao_hex: str) -> bool:
        """Check if icao_hex falls within any military Mode S allocation range."""
        try:
            val = int(icao_hex, 16)
        except (ValueError, TypeError):
            return False

        idx = bisect.bisect_right(self.starts, val) - 1
        if idx >= 0:
            start, end = self.ranges[idx]
            if start <= val <= end:
                return True
        return False


# ==============================================================================
# 3. EWS Mission & Threat Classification Engine
# ==============================================================================

AEW_TYPES = {
    "E3CF", "E3TF", "E2", "E737", "A50", "G550", "FA20", "SB37",
    "B737", "IL76", "E145", "SAAB"
}
AEW_KEYWORDS = ("AWACS", "SENTRY", "HAWKEYE", "GLOBALEYE", "WEDGETAIL", "MAINSTAY", "AEW&C", "CAEW", "AIRBORNE EARLY WARNING")

RECON_TYPES = {
    "RC135", "U2", "P8", "P3", "MQ9", "RQ4", "EP3", "C160", "TU214", "TU154",
    "BE20", "BE35", "GL5T", "CL60", "SENTINEL", "R1", "SHADOW"
}
RECON_KEYWORDS = ("RIVET JOINT", "POSEIDON", "DRAGON LADY", "GLOBAL HAWK", "REAPER", "SENTINEL", "RECONNAISSANCE", "SURVEILLANCE", "ISR", "SIGINT")

FIGHTER_TYPES = {
    "F16", "F18", "F22", "F35", "EUFI", "M2000", "RAF", "SU27", "SU30", "SU34",
    "SU35", "SU57", "MG29", "MG31", "J10", "J20", "JAS39", "T50", "FA50", "M346",
    "A10", "SU25", "AV8B", "TOR", "F15", "J8B", "JH7", "F5", "F4"
}

BOMBER_TYPES = {
    "B1", "B2", "B52", "TU22", "TU95", "TU160", "H6"
}

TANKER_TYPES = {
    "K35R", "KC10", "KC46", "A332", "IL78", "KC390", "A310"
}
TANKER_KEYWORDS = ("STRATOTANKER", "PEGASUS", "EXTENDER", "REFUEL", "TANKER", "MRTT")

TRANSPORT_TYPES = {
    "C17", "C130", "C30J", "A400", "IL76", "AN12", "AN26", "AN72", "AN124",
    "AN225", "C295", "C27J", "CN35", "V22", "C5M", "C2"
}

HELICOPTER_TYPES = {
    "AH64", "MI24", "MI28", "KA52", "UH60", "CH47", "NH90", "EC65", "T129",
    "UH1", "AS32", "AS65", "A109", "A129", "A139", "S92", "MI8", "MI17", "CH53"
}

VIP_KEYWORDS = ("AIR FORCE ONE", "STATE", "GOVERNMENT", "VIP", "PRESIDENTIAL", "ROYAL AIR FORCE", "KINGS FLIGHT", "EXECUTIVE TRANSPORT")

SAR_KEYWORDS = ("SEARCH AND RESCUE", "SAR", "MEDEVAC", "AMBULANCE", "COAST GUARD", "LIFEGUARD", "EMERGENCY")


def classify_ews_category(
    icao: str,
    type_code: Optional[str],
    flags: Optional[str],
    military: bool,
    description: Optional[str] = None,
    operator: Optional[str] = None
) -> str:
    """
    Classify aircraft into high-confidence EWS tactical / mission profile category.
    """
    tc = (type_code or "").upper().strip()
    desc = (description or "").upper().strip()
    op = (operator or "").upper().strip()

    # Priority 1: AEW&C / AWACS
    if any(k in desc for k in AEW_KEYWORDS) or any(k in op for k in AEW_KEYWORDS):
        return "MIL_AEW_C"
    if military and tc in AEW_TYPES and ("SURV" in desc or "RADAR" in desc or "EARLY" in desc):
        return "MIL_AEW_C"

    # Priority 2: Reconnaissance / ISR / SIGINT
    if any(k in desc for k in RECON_KEYWORDS) or any(k in op for k in RECON_KEYWORDS):
        return "MIL_RECON_ISR"
    if military and tc in RECON_TYPES:
        return "MIL_RECON_ISR"

    # Priority 3: Strategic Bomber
    if tc in BOMBER_TYPES or "BOMBER" in desc:
        return "MIL_BOMBER"

    # Priority 4: Fighter / Attack
    if tc in FIGHTER_TYPES or "FIGHTER" in desc:
        return "MIL_FIGHTER"

    # Priority 5: Tanker / Refueling
    if any(k in desc for k in TANKER_KEYWORDS) or any(k in op for k in TANKER_KEYWORDS):
        return "MIL_TANKER"
    if military and tc in TANKER_TYPES and "TANKER" in desc:
        return "MIL_TANKER"

    # Priority 6: State / Presidential VIP
    if any(k in desc for k in VIP_KEYWORDS) or any(k in op for k in VIP_KEYWORDS):
        return "STATE_VIP"

    # Priority 7: SAR / Emergency Medical
    if any(k in desc for k in SAR_KEYWORDS) or any(k in op for k in SAR_KEYWORDS):
        return "EMERGENCY_SAR"

    # Priority 8: Military Transport
    if tc in TRANSPORT_TYPES or (military and "TRANSPORT" in desc):
        return "MIL_TRANSPORT"

    # Priority 9: Military Rotorcraft
    if tc in HELICOPTER_TYPES or (military and ("HELI" in desc or "ROTOR" in desc)):
        return "MIL_HELICOPTER"

    # Fallbacks based on military flag
    if military:
        return "MIL_OTHER"

    # Civil classifications
    if op and ("AIRLINES" in op or "AIRWAYS" in op or "CARGO" in op or "FREIGHT" in op):
        return "CIVIL_COMMERCIAL"

    return "CIVIL_GENERAL"


# ==============================================================================
# 4. SQLite Database Builder (Issue #19 Solution & EWS Query Store)
# ==============================================================================

SQL_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS aircraft (
    icao TEXT PRIMARY KEY,
    registration TEXT,
    type_code TEXT,
    flags TEXT,
    description TEXT,
    year TEXT,
    operator TEXT,
    country_code TEXT,
    country_name TEXT,
    is_military INTEGER NOT NULL DEFAULT 0,
    ews_category TEXT NOT NULL DEFAULT 'CIVIL_GENERAL'
);

CREATE INDEX IF NOT EXISTS idx_aircraft_reg ON aircraft(registration);
CREATE INDEX IF NOT EXISTS idx_aircraft_type ON aircraft(type_code);
CREATE INDEX IF NOT EXISTS idx_aircraft_mil ON aircraft(is_military);
CREATE INDEX IF NOT EXISTS idx_aircraft_ews ON aircraft(ews_category);
CREATE INDEX IF NOT EXISTS idx_aircraft_country ON aircraft(country_code);

CREATE TABLE IF NOT EXISTS military_ranges (
    start_hex TEXT PRIMARY KEY,
    end_hex TEXT,
    start_int INTEGER,
    end_int INTEGER
);

CREATE TABLE IF NOT EXISTS db_metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def build_sqlite_db(
    csv_path: str,
    ranges_path: str,
    output_db_path: str,
    batch_size: int = 15000,
    progress_callback: Optional[Any] = None
) -> int:
    """
    Ingest aircraft.csv and ranges.json into a high-performance SQLite database.
    Returns total rows inserted.
    """
    matcher = MilitaryRangeMatcher.from_ranges_json(ranges_path)

    if os.path.exists(output_db_path):
        os.remove(output_db_path)

    conn = sqlite3.connect(output_db_path, isolation_level=None)
    cur = conn.cursor()
    cur.executescript(SQL_SCHEMA)

    # Insert military ranges
    cur.execute("BEGIN TRANSACTION")
    for s_int, e_int in matcher.ranges:
        cur.execute(
            "INSERT INTO military_ranges (start_hex, end_hex, start_int, end_int) VALUES (?, ?, ?, ?)",
            (f"{s_int:06X}", f"{e_int:06X}", s_int, e_int)
        )
    cur.execute("COMMIT")

    # Open CSV (supporting .csv or .csv.gz)
    is_gz = csv_path.endswith(".gz")
    open_func = gzip.open if is_gz else open

    rows_batch = []
    total_count = 0

    insert_sql = """
    INSERT OR REPLACE INTO aircraft (
        icao, registration, type_code, flags, description, year, operator,
        country_code, country_name, is_military, ews_category
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    with open_func(csv_path, "rt", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f, delimiter=";", quotechar=None, escapechar="\\")
        cur.execute("BEGIN TRANSACTION")

        for row in reader:
            if not row or len(row) < 3:
                continue
            icao = row[0].strip().upper()
            if len(icao) != 6:
                continue

            reg = row[1].strip() if len(row) > 1 and row[1] else None
            type_code = row[2].strip() if len(row) > 2 and row[2] else None
            flags = row[3].strip() if len(row) > 3 and row[3] else None
            desc = row[4].strip() if len(row) > 4 and row[4] else None
            year = row[5].strip() if len(row) > 5 and row[5] else None
            ownop = row[6].strip() if len(row) > 6 and row[6] else None

            # Check military via bitmask flag or Mode S ranges.json
            flag_mil = bool(flags and flags.startswith("1"))
            range_mil = matcher.is_military(icao)
            is_military = 1 if (flag_mil or range_mil) else 0

            # Country resolution
            country_code, country_name = resolve_country(icao)

            # EWS categorization
            ews_cat = classify_ews_category(
                icao=icao,
                type_code=type_code,
                flags=flags,
                military=bool(is_military),
                description=desc,
                operator=ownop
            )

            rows_batch.append((
                icao, reg, type_code, flags, desc, year, ownop,
                country_code, country_name, is_military, ews_cat
            ))
            total_count += 1

            if len(rows_batch) >= batch_size:
                cur.executemany(insert_sql, rows_batch)
                rows_batch.clear()
                if progress_callback:
                    progress_callback(total_count)

        if rows_batch:
            cur.executemany(insert_sql, rows_batch)
            rows_batch.clear()

        # Record metadata
        cur.execute("INSERT OR REPLACE INTO db_metadata (key, value) VALUES ('row_count', ?)", (str(total_count),))
        cur.execute("INSERT OR REPLACE INTO db_metadata (key, value) VALUES ('schema_version', '1.0')")
        cur.execute("INSERT OR REPLACE INTO db_metadata (key, value) VALUES ('generator', 'tar1090-db ews.py')")
        cur.execute("COMMIT")

    conn.close()
    return total_count


# ==============================================================================
# 5. Fast Query Client
# ==============================================================================

class EWSClient:
    """Client for querying the SQLite EWS aircraft database."""

    def __init__(self, db_path: str = "aircraft.sqlite"):
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database not found: {db_path}")
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def lookup(self, icao: str) -> Optional[Dict[str, Any]]:
        """Look up aircraft details by 6-character ICAO hex code."""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM aircraft WHERE icao = ?", (icao.upper().strip(),))
        row = cur.fetchone()
        return dict(row) if row else None

    def query_category(self, ews_category: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Query aircraft by EWS category (e.g. MIL_AEW_C, MIL_FIGHTER, STATE_VIP)."""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM aircraft WHERE ews_category = ? LIMIT ?",
            (ews_category, limit)
        )
        return [dict(r) for r in cur.fetchall()]

    def stats(self) -> Dict[str, Any]:
        """Return summary statistics by category and military status."""
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM aircraft")
        total = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM aircraft WHERE is_military = 1")
        total_mil = cur.fetchone()[0]

        cur.execute("SELECT ews_category, COUNT(*) FROM aircraft GROUP BY ews_category ORDER BY COUNT(*) DESC")
        cat_counts = dict(cur.fetchall())

        return {
            "total_aircraft": total,
            "military_aircraft": total_mil,
            "categories": cat_counts
        }

    def close(self):
        self.conn.close()


# ==============================================================================
# 6. Command Line Interface
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="EWS (Early Warning System) & ADS-B Aircraft Database Utility for tar1090-db."
    )
    parser.add_argument("--build", action="store_true", help="Build SQLite database from aircraft.csv and ranges.json")
    parser.add_argument("--csv", default="aircraft.csv", help="Path to aircraft.csv or aircraft.csv.gz (default: aircraft.csv)")
    parser.add_argument("--ranges", default="ranges.json", help="Path to ranges.json (default: ranges.json)")
    parser.add_argument("--db", default="aircraft.sqlite", help="Path to output/input SQLite database (default: aircraft.sqlite)")
    parser.add_argument("--lookup", type=str, help="Look up a 6-hex ICAO Mode S address")
    parser.add_argument("--query-category", type=str, help="List aircraft by EWS category (e.g. MIL_AEW_C, MIL_FIGHTER)")
    parser.add_argument("--stats", action="store_true", help="Show database summary statistics")
    parser.add_argument("--limit", type=int, default=25, help="Query results limit (default: 25)")

    args = parser.parse_args()

    if args.build:
        print(f"Building EWS SQLite database '{args.db}' from '{args.csv}' and '{args.ranges}'...")
        count = build_sqlite_db(
            csv_path=args.csv,
            ranges_path=args.ranges,
            output_db_path=args.db,
            progress_callback=lambda c: sys.stdout.write(f"\rIngested {c} aircraft...")
        )
        print(f"\nDone! Ingested {count} aircraft into {args.db}")
        return

    if args.lookup:
        client = EWSClient(args.db)
        res = client.lookup(args.lookup)
        if res:
            print(json.dumps(res, indent=2))
        else:
            print(f"ICAO {args.lookup.upper()} not found in database.")
        client.close()
        return

    if args.query_category:
        client = EWSClient(args.db)
        rows = client.query_category(args.query_category, limit=args.limit)
        print(f"Found {len(rows)} aircraft for category {args.query_category}:")
        for r in rows:
            print(f"  {r['icao']} | {r['registration'] or 'NO-REG':<8} | {r['type_code'] or '????':<5} | {r['country_code'] or '??'} | {r['description'] or ''}")
        client.close()
        return

    if args.stats:
        client = EWSClient(args.db)
        stats = client.stats()
        print(json.dumps(stats, indent=2))
        client.close()
        return

    parser.print_help()


if __name__ == "__main__":
    main()
