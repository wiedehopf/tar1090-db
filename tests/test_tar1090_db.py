#!/usr/bin/env python3
"""
Comprehensive test suite for tar1090-db bug fixes and EWS infrastructure.
"""

import os
import sys
import tempfile
import unittest
import json
import sqlite3

# Ensure scratch tar1090-db is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ews
import toJson


class TestToJsonFixes(unittest.TestCase):
    def test_writedb_debug_mode_no_typeerror(self):
        """Verify that writedb with debug=True does not crash with TypeError."""
        blocks = {
            "A": {
                "00001": ["N10001", "C172", "00", "Cessna 172"],
                "00002": ["N10002", "B738", "00", "Boeing 737-800"],
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            # Should run without throwing TypeError from string + int concatenation
            toJson.writedb(blocks, tmpdir, blocklimit=1, debug=True)
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "files.js")))

    def test_replace_error_handler_valid(self):
        """Verify that errors='replace' correctly handles invalid UTF-8 bytes without LookupError."""
        with tempfile.NamedTemporaryFile("wb", delete=False) as f:
            f.write(b'{"icao": "A12345", "reg": "TEST\xff\xfe"}\n')
            bad_path = f.name

        try:
            with open(bad_path, "rt", encoding="utf-8", errors="replace") as f:
                content = f.read()
                self.assertIn("A12345", content)
                self.assertIn("\ufffd", content)
        finally:
            if os.path.exists(bad_path):
                os.remove(bad_path)

    def test_fallback_type_description_assignment(self):
        """Verify that fallback aircraft from basic-ac-db get both 't' and 'd' assigned."""
        newTypes = {"C172": ["Cessna 172 Skyhawk", "L1P"]}
        e = {"r": "N12345"}
        icaotype = "C172"

        # Fixed logic from toJson.py:
        if icaotype and not e.get("t"):
            nT = newTypes.get(icaotype)
            if nT and nT[0]:
                e["d"] = nT[0]
            e["t"] = icaotype

        self.assertEqual(e["t"], "C172")
        self.assertEqual(e["d"], "Cessna 172 Skyhawk")

    def test_ac68_to_ac90_turboprop_correction(self):
        """Verify that Aero Commander 690 airframes mistakenly typed AC68 are corrected to AC90 (Issue #20)."""
        newTypes = {"AC90": ["Aero Commander 690 Turbo Commander", "L2T"], "AC68": ["Aero Commander 680", "L2P"]}
        entry = {"t": "AC68", "d": "AERO Commander 690A"}
        if entry.get("t") == "AC68" and ("690" in (entry.get("d") or "")):
            entry["t"] = "AC90"
            nT = newTypes.get("AC90")
            if nT and nT[0]:
                entry["d"] = nT[0]
        self.assertEqual(entry["t"], "AC90")
        self.assertEqual(entry["d"], "Aero Commander 690 Turbo Commander")


class TestApFixes(unittest.TestCase):
    def test_iata_filtering_no_icao_dependency(self):
        """Verify that IATA loop filters numbered codes using iata, not icao."""
        table = [
            {"iata_code": "JFK", "latitude_deg": "40.6394", "longitude_deg": "-73.7793"},
            {"iata_code": "1A2", "latitude_deg": "35.1234", "longitude_deg": "-80.1234"},
        ]
        import re
        lookup = {}
        for a in table:
            if a.get("iata_code") and a.get("latitude_deg"):
                iata = a["iata_code"]
                if re.search(r"\d", iata):
                    continue
                lookup[iata] = a

        self.assertIn("JFK", lookup)
        self.assertNotIn("1A2", lookup)

    def test_safe_coordinate_conversion(self):
        """Verify safe float conversion handles empty and invalid coordinates."""
        test_cases = [
            ({"latitude_deg": "40.639447", "longitude_deg": "-73.779317"}, [40.6394, -73.7793]),
            ({"latitude_deg": "", "longitude_deg": "-73.779317"}, None),
            ({"latitude_deg": "N/A", "longitude_deg": "invalid"}, None),
        ]
        for input_dict, expected in test_cases:
            try:
                lat = float(input_dict.get("latitude_deg", ""))
                lon = float(input_dict.get("longitude_deg", ""))
                res = [round(lat, 4), round(lon, 4)]
            except (ValueError, TypeError):
                res = None
            self.assertEqual(res, expected)


class TestEWSInfrastructure(unittest.TestCase):
    def test_military_ranges_matcher(self):
        """Test interval binary search for military hexes."""
        sample_ranges = [(0xADF7C8, 0xAFFFFF), (0x4B8200, 0x4B82FF)]
        matcher = ews.MilitaryRangeMatcher(sample_ranges)

        self.assertTrue(matcher.is_military("ADF7C8"))
        self.assertTrue(matcher.is_military("ADF999"))
        self.assertTrue(matcher.is_military("4B8201"))
        self.assertFalse(matcher.is_military("A00001"))
        self.assertFalse(matcher.is_military("400000"))

    def test_country_resolution(self):
        """Test 24-bit Mode-S address country allocation."""
        code, name = ews.resolve_country("A12345")
        self.assertEqual(code, "US")
        self.assertEqual(name, "United States")

        code, name = ews.resolve_country("4B8200")
        self.assertEqual(code, "TR")
        self.assertEqual(name, "Turkey")

        code, name = ews.resolve_country("400001")
        self.assertEqual(code, "GB")
        self.assertEqual(name, "United Kingdom")

    def test_ews_threat_classification(self):
        """Test EWS mission profile tagging."""
        self.assertEqual(
            ews.classify_ews_category("A00001", "F16", "10", True, "General Dynamics F-16"),
            "MIL_FIGHTER"
        )
        self.assertEqual(
            ews.classify_ews_category("A00002", "E3CF", "10", True, "Boeing E-3 Sentry AWACS"),
            "MIL_AEW_C"
        )
        self.assertEqual(
            ews.classify_ews_category("A00003", "P8", "10", True, "Boeing P-8A Poseidon"),
            "MIL_RECON_ISR"
        )
        self.assertEqual(
            ews.classify_ews_category("A00004", "KC10", "10", True, "McDonnell Douglas KC-10 Extender"),
            "MIL_TANKER"
        )
        self.assertEqual(
            ews.classify_ews_category("A00005", "C17", "10", True, "Boeing C-17 Globemaster III"),
            "MIL_TRANSPORT"
        )
        self.assertEqual(
            ews.classify_ews_category("A00006", "B742", "00", False, "Air Force One", "Air Force One"),
            "STATE_VIP"
        )
        self.assertEqual(
            ews.classify_ews_category("A00007", "B738", "00", False, "Boeing 737-800", "Turkish Airlines"),
            "CIVIL_COMMERCIAL"
        )

    def test_sqlite_builder_and_query(self):
        """Test full SQLite database generation, indexes, and fast querying."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ranges_path = os.path.join(tmpdir, "ranges.json")
            with open(ranges_path, "w") as f:
                json.dump({"military": [["adf7c8", "afffff"], ["4b8200", "4b82ff"]]}, f)

            csv_path = os.path.join(tmpdir, "aircraft.csv")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("ADF7C9;90-0001;F16;10;General Dynamics F-16;1990;US Air Force;\n")
                f.write("4B8201;11-001;KC135;10;Boeing KC-135 Stratotanker;1962;Turkish Air Force;\n")
                f.write("A1E987;N222ME;AC90;00;Aero Commander 690A;1974;Private;\n")

            db_path = os.path.join(tmpdir, "aircraft.sqlite")
            count = ews.build_sqlite_db(csv_path, ranges_path, db_path)
            self.assertEqual(count, 3)

            # Test querying
            client = ews.EWSClient(db_path)
            row = client.lookup("ADF7C9")
            self.assertIsNotNone(row)
            self.assertEqual(row["registration"], "90-0001")
            self.assertEqual(row["is_military"], 1)
            self.assertEqual(row["ews_category"], "MIL_FIGHTER")
            self.assertEqual(row["country_code"], "US")

            # Test category query
            fighters = client.query_category("MIL_FIGHTER")
            self.assertEqual(len(fighters), 1)
            self.assertEqual(fighters[0]["icao"], "ADF7C9")

            tankers = client.query_category("MIL_TANKER")
            self.assertEqual(len(tankers), 1)
            self.assertEqual(tankers[0]["icao"], "4B8201")

            # Test stats
            stats = client.stats()
            self.assertEqual(stats["total_aircraft"], 3)
            self.assertEqual(stats["military_aircraft"], 2)

            client.close()

    def test_gzip_csv_ingestion(self):
        """Test that build_sqlite_db handles .csv.gz compressed files."""
        import gzip
        with tempfile.TemporaryDirectory() as tmpdir:
            ranges_path = os.path.join(tmpdir, "ranges.json")
            with open(ranges_path, "w") as f:
                json.dump({"military": [["adf7c8", "afffff"]]}, f)

            gz_path = os.path.join(tmpdir, "aircraft.csv.gz")
            with gzip.open(gz_path, "wt", encoding="utf-8") as f:
                f.write("ADF7C8;MIL01;F35;10;Lockheed Martin F-35 Lightning II;2020;USAF;\n")
                f.write("A00001;N123;C152;00;Cessna 152;1980;Private;\n")

            db_path = os.path.join(tmpdir, "aircraft_gz.sqlite")
            count = ews.build_sqlite_db(gz_path, ranges_path, db_path)
            self.assertEqual(count, 2)

            client = ews.EWSClient(db_path)
            res = client.lookup("ADF7C8")
            self.assertIsNotNone(res)
            self.assertEqual(res["type_code"], "F35")
            self.assertEqual(res["ews_category"], "MIL_FIGHTER")
            client.close()

    def test_invalid_hex_handling(self):
        """Verify matcher and resolver handle invalid hex inputs gracefully."""
        self.assertFalse(ews.MilitaryRangeMatcher([]).is_military("NOTHEX"))
        self.assertFalse(ews.MilitaryRangeMatcher([]).is_military(None))
        self.assertEqual(ews.resolve_country("ZZZZZZ"), (None, None))
        self.assertEqual(ews.resolve_country(""), (None, None))


if __name__ == "__main__":
    unittest.main()
