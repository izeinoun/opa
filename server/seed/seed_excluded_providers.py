"""Seed the excluded_providers reference table from the CMS/OIG LEIE.

Source: the LEIE (List of Excluded Individuals/Entities) CSV. Only rows with a
valid 10-digit NPI are loaded — `npi` is the deterministic join key DET-08
screens each claim's rendering provider against. Name+DOB-only individuals
(NPI = 0000000000) are intentionally out of scope for the NPI match.

The trimmed source ships at seed/data/leie_npi.csv so production deploys can
self-seed without the full 15 MB file. Synchronous sqlite3; idempotent.
"""
from __future__ import annotations

import csv
import os
import sqlite3
from datetime import datetime
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "leie_npi.csv")


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value or value in ("00000000", "0000000000"):
        return None
    return value


def run(db_path: str = DB_PATH) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        existing = conn.execute("SELECT COUNT(*) FROM excluded_providers").fetchone()[0]
        if existing:
            print(f"  excluded_providers already seeded ({existing} rows) — skipping")
            return {"inserted": 0, "skipped": existing}

        if not os.path.exists(DATA_FILE):
            print(f"  LEIE data file not found at {DATA_FILE} — skipping")
            return {"inserted": 0}

        now = datetime.utcnow().isoformat()
        rows = []
        with open(DATA_FILE, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                npi = _clean(r.get("NPI"))
                if not (npi and npi.isdigit() and len(npi) == 10):
                    continue
                rows.append((
                    str(uuid4()),
                    npi,
                    _clean(r.get("LASTNAME")),
                    _clean(r.get("FIRSTNAME")),
                    _clean(r.get("MIDNAME")),
                    _clean(r.get("BUSNAME")),
                    _clean(r.get("GENERAL")),
                    _clean(r.get("SPECIALTY")),
                    _clean(r.get("UPIN")),
                    _clean(r.get("DOB")),
                    _clean(r.get("ADDRESS")),
                    _clean(r.get("CITY")),
                    _clean(r.get("STATE")),
                    _clean(r.get("ZIP")),
                    _clean(r.get("EXCLTYPE")),
                    _clean(r.get("EXCLDATE")),
                    _clean(r.get("REINDATE")),
                    _clean(r.get("WAIVERDATE")),
                    _clean(r.get("WVRSTATE")),
                    "OIG LEIE",
                    now,
                ))

        conn.executemany(
            "INSERT INTO excluded_providers ("
            "excluded_provider_id, npi, last_name, first_name, middle_name, "
            "business_name, general_category, specialty, upin, dob, address, "
            "city, state, zip_code, exclusion_type, exclusion_date, "
            "reinstate_date, waiver_date, waiver_state, source, created_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        print(f"  Inserted {len(rows)} excluded providers (OIG LEIE, NPI-bearing)")
        return {"inserted": len(rows)}
    finally:
        conn.close()


if __name__ == "__main__":
    run()
