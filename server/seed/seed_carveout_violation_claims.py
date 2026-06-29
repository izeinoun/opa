"""Seed HMO carve-out violation claims that exercise DET-20.

Creates three demo claims whose carve-out signals ride along in
`claims.raw_claim_json` (the claim envelope DET-20 reads):
1. Behavioral health from an out-of-network provider        -> CARVEOUT_NO_NETWORK
2. Behavioral health visit 25+ without pre-authorization    -> CARVEOUT_PREAUTH_REQUIRED
3. DME from a non-approved vendor                            -> CARVEOUT_UNAPPROVED_VENDOR

Columns are aligned with the live `claims` / `claim_lines` schema (NOT the older
ClaimGuard schema the first draft was written against).
"""
from __future__ import annotations

import os
import sqlite3
import json
from datetime import datetime, timedelta
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
TODAY = datetime.now().date()

_CLAIM_COLS = (
    "claim_id, icn, member_id, provider_org_id, billing_provider_npi, "
    "rendering_provider_npi, lob, service_from_date, service_to_date, claim_type, "
    "claim_form_type, care_setting, description, claim_status, total_billed, "
    "total_paid, submission_date, pos_code, primary_icd, pipeline_mode, "
    "raw_claim_json, created_at, updated_at"
)
_LINE_COLS = (
    "claim_line_id, claim_id, line_number, cpt_code, service_date, diag_1, "
    "units_billed, units_paid, billed_amount, paid_amount, allowed_amount, pos_code"
)


def run(db_path: str = DB_PATH) -> int:
    """Seed carve-out violation claims for DET-20."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT provider_org_id, name, npi FROM provider_orgs LIMIT 1")
        provider_row = cursor.fetchone()
        if not provider_row:
            print("  No providers found — skipping carve-out violation claims")
            return 0
        provider_id, _provider_name, provider_npi = provider_row

        cursor.execute("SELECT member_id, member_number FROM members LIMIT 1")
        member_row = cursor.fetchone()
        if not member_row:
            print("  No members found — skipping carve-out violation claims")
            return 0
        member_id, _member_number = member_row

        now = datetime.now().isoformat()

        def claim_row(claim_id, svc_date, claim_type, desc, total, primary_icd, pos, raw_json):
            return (
                claim_id, str(uuid4())[:20], member_id, provider_id,
                provider_npi, provider_npi, "HMO", svc_date, svc_date, claim_type,
                "CMS-1500", "Outpatient", desc, "paid", total,
                total, svc_date, pos, primary_icd, "post_pay",
                raw_json, now, now,
            )

        def line_row(claim_id, cpt, total, diag, pos):
            return (
                str(uuid4()), claim_id, 1, cpt, None, diag,
                1, 1, total, total, total, pos,
            )

        claims_to_insert = []
        claim_lines_to_insert = []

        # CLAIM 1: Behavioral health — out-of-network without authorization.
        claim_id_1 = str(uuid4())
        svc_1 = (TODAY - timedelta(days=10)).isoformat()
        raw_1 = json.dumps({
            "provider_network": False,
            "behavioral_health_preauth": False,
            "bh_visit_count": 1,
            "violation_reason": "Behavioral health from out-of-network provider",
        })
        claims_to_insert.append(claim_row(
            claim_id_1, svc_1, "professional",
            "Psychotherapy for depression - out-of-network", 750.00, "F32.9", "11", raw_1,
        ))
        claim_lines_to_insert.append(line_row(claim_id_1, "90834", 750.00, "F32.9", "11"))

        # CLAIM 2: Behavioral health — visit 25+ without pre-authorization.
        claim_id_2 = str(uuid4())
        svc_2 = (TODAY - timedelta(days=5)).isoformat()
        raw_2 = json.dumps({
            "provider_network": True,
            "behavioral_health_preauth": False,
            "bh_visit_count": 25,
            "violation_reason": "Behavioral health visit 25+ without pre-authorization",
        })
        claims_to_insert.append(claim_row(
            claim_id_2, svc_2, "professional",
            "Psychotherapy for anxiety - 25th visit without authorization", 600.00, "F41.9", "11", raw_2,
        ))
        claim_lines_to_insert.append(line_row(claim_id_2, "90837", 600.00, "F41.9", "11"))

        # CLAIM 3: DME — non-approved vendor.
        claim_id_3 = str(uuid4())
        svc_3 = (TODAY - timedelta(days=3)).isoformat()
        raw_3 = json.dumps({
            "provider_network": True,
            "dme_vendor": "MedSupply Plus (non-approved)",
            "violation_reason": "DME supplied by non-approved vendor",
        })
        claims_to_insert.append(claim_row(
            claim_id_3, svc_3, "professional",
            "CPAP machine rental from non-network vendor", 450.00, "G47.33", "12", raw_3,
        ))
        claim_lines_to_insert.append(line_row(claim_id_3, "E1600", 450.00, "G47.33", "12"))

        cursor.executemany(
            f"INSERT INTO claims ({_CLAIM_COLS}) VALUES ({','.join('?' * 23)})",
            claims_to_insert,
        )
        cursor.executemany(
            f"INSERT INTO claim_lines ({_LINE_COLS}) VALUES ({','.join('?' * 12)})",
            claim_lines_to_insert,
        )
        conn.commit()

        print(f"  Inserted {len(claims_to_insert)} carve-out violation claims")
        print("    - Behavioral Health (out-of-network, no auth)")
        print("    - Behavioral Health (visit 25+, no auth)")
        print("    - DME (non-approved vendor)")
        print("  These demonstrate DET-20 carve-out violation detection")

        return len(claims_to_insert)

    except Exception as e:
        print(f"  Error seeding carve-out violation claims: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run()
