"""Seed provider_orgs and providers — synchronous sqlite3.

NPIs match seed_training_data.py profiles exactly.
billing_variance_score seeded at 0.5; ML training overwrites these values.
"""
from __future__ import annotations

import os
import sqlite3
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW = "2024-01-01T08:00:00"

# (name, org_npi, tin, org_type, is_sensitive)
ORGS = [
    ("Midwest Cardiac & Specialty Group",  "9900000001", "36-1000001", "physician_group",    0),
    ("Lakeside Multi-Specialty Associates", "9900000002", "36-2000002", "physician_group",    0),
    ("North Shore Rehabilitation Network", "9900000003", "36-3000003", "rehabilitation",      0),
]

# (npi, name, specialty, org_index, tin, credential_status,
#  credential_effective_date, is_excluded, exclusion_source)
PROVIDERS = [
    # Org 0 — Midwest Cardiac
    ("1111111111", "Dr. Elena Vasquez",   "Cardiology",           0, "36-1000001",
     "active", "2020-01-01", 0, None),
    ("1111111112", "Dr. Mark Ohlsson",    "Orthopedic Surgery",   0, "36-1000001",
     "active", "2019-06-01", 0, None),
    ("1111111113", "Dr. Sandra Fitch",    "Neurology",            0, "36-1000001",
     "active", "2021-03-01", 0, None),
    ("1111111114", "Dr. Grant Abrams",    "Internal Medicine",    0, "36-1000001",
     "active", "2018-09-01", 0, None),
    # NPI 1700942034 is a real OIG LEIE-excluded individual (Angela Giron,
    # Internal Medicine). Seeded into the roster so the DET-08 demo claim
    # resolves a provider name; the exclusion is driven by the LEIE table
    # (seed_excluded_providers), NOT a manual is_excluded flag.
    ("1700942034", "Dr. Angela Giron",    "Internal Medicine",    0, "36-1000001",
     "active", "2021-02-01", 0, None),
    # Org 1 — Lakeside Multi-Specialty
    ("2222222221", "Dr. Yuki Tanaka",     "Cardiology",           1, "36-2000002",
     "active", "2020-07-01", 0, None),
    ("2222222222", "Dr. Carlos Medina",   "Emergency Medicine",   1, "36-2000002",
     "active", "2017-04-01", 0, None),
    ("2222222223", "Dr. Fatima Al-Rashid","Internal Medicine",    1, "36-2000002",
     "active", "2022-01-01", 0, None),
    # Org 2 — North Shore Rehab
    ("3333333331", "Dr. Paul Eriksson",   "Orthopedic Surgery",   2, "36-3000003",
     "active", "2019-11-01", 0, None),
    ("3333333332", "Dr. Nina Okafor",     "Radiology",            2, "36-3000003",
     "active", "2021-08-01", 0, None),
    ("3333333333", "Dr. Luis Montoya",    "Physical Therapy",     2, "36-3000003",
     "active", "2020-05-01", 0, None),
]


def run(db_path: str = DB_PATH) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        if conn.execute("SELECT COUNT(*) FROM providers").fetchone()[0]:
            print("  providers already seeded — skipping")
            return {}

        # Insert orgs
        org_ids: list[str] = []
        for name, npi, tin, org_type, sensitive in ORGS:
            oid = str(uuid4())
            org_ids.append(oid)
            conn.execute(
                "INSERT INTO provider_orgs "
                "(provider_org_id, name, npi, tin, org_type, is_sensitive, risk_score, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (oid, name, npi, tin, org_type, sensitive, 0.0, NOW, NOW),
            )

        # Insert providers (billing_variance_score=0.5 — ML will overwrite)
        npi_to_provider_id: dict[str, str] = {}
        for (npi, name, specialty, org_idx, tin, cred_status,
             cred_eff, is_excl, excl_src) in PROVIDERS:
            pid = str(uuid4())
            npi_to_provider_id[npi] = pid
            conn.execute(
                "INSERT INTO providers "
                "(provider_id, provider_org_id, npi, tin, name, specialty, "
                "credential_status, credential_effective_date, is_excluded, "
                "exclusion_source, billing_variance_score, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, org_ids[org_idx], npi, tin, name, specialty,
                 cred_status, cred_eff, is_excl,
                 excl_src, 0.5, NOW, NOW),
            )

        conn.commit()
        print(f"  Inserted {len(ORGS)} orgs, {len(PROVIDERS)} providers")
        return npi_to_provider_id
    finally:
        conn.close()


if __name__ == "__main__":
    run()
