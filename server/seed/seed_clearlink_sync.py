"""Seed ClearLink sync data — members and providers from ClearLink system.

This adds 3 ClearLink members and providers to OPA so they can be referenced
in MCP calls to the ClearLink system. Creates provider orgs as needed to satisfy
OPA's ProviderOrg foreign key constraint (ClearLink has no org model).

Data sourced from ClearLink's member/provider database.
"""
from __future__ import annotations

import os
import sqlite3
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW = "2024-01-01T08:00:00"

# ClearLink Provider Organizations (needed for OPA's ProviderOrg FK constraint)
# practice_name mapped from ClearLink providers
CLEARLINK_ORGS = [
    ("Capital Primary Care", "9999000001", "36-9000001", "physician_practice", 0),
    ("Arlington Senior Medical Group", "9999000002", "36-9000002", "physician_practice", 0),
    ("Capital Heart & Vascular", "9999000003", "36-9000003", "physician_practice", 0),
]

# ClearLink Providers (mapped to org index)
# ClearLink data: Dr. Harry Clancy, Dr. Linda Marsh, Dr. John McCane
CLEARLINK_PROVIDERS = [
    ("9999111111", "Dr. Harry Clancy", "Primary Care", 0, "36-9000001",
     "active", "2020-01-01", 0, None),
    ("9999111112", "Dr. Linda Marsh", "Internal Medicine", 1, "36-9000002",
     "active", "2021-06-01", 0, None),
    ("9999111113", "Dr. John McCane", "Cardiology", 2, "36-9000003",
     "active", "2019-03-01", 0, None),
]

# ClearLink Members (to be added to OPA for MCP testing)
# member_number matches ClearLink's member_id for easy cross-reference
CLEARLINK_MEMBERS = [
    ("Stacy", "Truman", "1975-05-14", "MA", "2020-01-01", None, None, None, "CL-123456"),
    ("Robert", "Hargrove", "1962-08-22", "MA", "2019-06-01", None, None, None, "CL-789012"),
    ("Lauren", "Chen", "1988-11-03", "MA", "2021-03-01", None, None, None, "CL-345678"),
]


def run(db_path: str = DB_PATH) -> int:
    """Seed ClearLink data into OPA. Returns count of new rows added."""
    conn = sqlite3.connect(db_path)
    try:
        # Check if already seeded (check for one of the ClearLink orgs)
        existing = conn.execute(
            "SELECT COUNT(*) FROM provider_orgs WHERE name LIKE 'Capital Primary%'"
        ).fetchone()[0]
        if existing:
            print("  ClearLink data already seeded — skipping")
            return 0

        # ── Provider Orgs ──────────────────────────────────────────────────
        org_ids = {}
        for (name, npi, tin, org_type, is_sensitive) in CLEARLINK_ORGS:
            org_id = str(uuid4())
            org_ids[name] = org_id
            conn.execute(
                """INSERT INTO provider_orgs
                   (provider_org_id, name, npi, tin, org_type, is_sensitive, risk_score, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (org_id, name, npi, tin, org_type, is_sensitive, 0.5, NOW, NOW),
            )

        # ── Providers ──────────────────────────────────────────────────────
        for (npi, name, specialty, org_idx, tin, cred_status, cred_eff, is_excl, excl_src) in CLEARLINK_PROVIDERS:
            provider_id = str(uuid4())
            # Map org_idx to org_id
            org_names = [org[0] for org in CLEARLINK_ORGS]
            org_id = org_ids[org_names[org_idx]]

            conn.execute(
                """INSERT INTO providers
                   (provider_id, provider_org_id, npi, tin, name, specialty,
                    credential_status, credential_effective_date, is_excluded,
                    exclusion_source, billing_variance_score, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (provider_id, org_id, npi, tin, name, specialty,
                 cred_status, cred_eff, is_excl, excl_src, 0.5, NOW, NOW),
            )

        # ── Members ────────────────────────────────────────────────────────
        for (first, last, dob, lob, cov_eff, cov_term, retro_term, dod, member_num) in CLEARLINK_MEMBERS:
            conn.execute(
                """INSERT INTO members
                   (member_id, member_number, first_name, last_name, date_of_birth,
                    date_of_death, lob, coverage_effective_date, coverage_termination_date,
                    retro_termination_date, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid4()), member_num, first, last, dob, dod, lob,
                 cov_eff, cov_term, retro_term, NOW, NOW),
            )

        conn.commit()
        count = 3 + 3 + 3  # orgs + providers + members
        print(f"  ✓ Seeded {count} ClearLink rows (3 orgs, 3 providers, 3 members)")
        return count

    finally:
        conn.close()


if __name__ == "__main__":
    run()
