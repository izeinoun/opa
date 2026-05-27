"""Seed reference_data_freshness — synchronous sqlite3.

6 sources with varying staleness levels. DMF and State Medicaid Rates are
flagged as stale/critical to exercise the freshness-check logic.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta

DB_PATH = os.getenv("DB_PATH", "./opa.db")

_BASE = datetime(2024, 1, 1, 8, 0, 0)


def _ago(days: int) -> str:
    return (_BASE - timedelta(days=days)).isoformat()


def _next(days: int) -> str:
    return (_BASE + timedelta(days=days)).isoformat()


# (source_name, last_refreshed_days_ago, next_refresh_days_out, status, affected_detectors)
SOURCES = [
    (
        "CMS Fee Schedule",
        7, 83, "fresh",
        ["fee_schedule_check", "allowed_amount_variance"],
    ),
    (
        "OIG Exclusion List",
        3, 27, "fresh",
        ["excluded_provider_detector", "sanction_check"],
    ),
    (
        "State Medicaid Rates",
        92, -2, "critical",  # overdue
        ["medicaid_rate_check", "fee_schedule_check"],
    ),
    (
        "DMF Death Master File",
        45, -15, "stale",   # overdue
        ["deceased_member_detector", "post_death_billing"],
    ),
    (
        "NPPES NPI Registry",
        14, 16, "fresh",
        ["provider_credential_check", "billing_provider_validation"],
    ),
    (
        "CPT Code Crosswalk",
        30, 60, "fresh",
        ["cpt_icd_mismatch_detector", "code_edit_detector"],
    ),
    (
        "NCCI Policy Manual",
        30, 60, "fresh",
        ["ncci_ptp_check", "mue_unit_check"],
    ),
]


def run(db_path: str = DB_PATH) -> int:
    conn = sqlite3.connect(db_path)
    try:
        if conn.execute("SELECT COUNT(*) FROM reference_data_freshness").fetchone()[0]:
            print("  reference_data_freshness already seeded — skipping")
            return 0

        for source_name, refreshed_ago, next_out, status, detectors in SOURCES:
            conn.execute(
                "INSERT INTO reference_data_freshness "
                "(source_name, last_refreshed_at, next_scheduled_refresh, "
                "status, affected_detectors, updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    source_name,
                    _ago(refreshed_ago),
                    _next(next_out),
                    status,
                    json.dumps(detectors),
                    _BASE.isoformat(),
                ),
            )

        conn.commit()
        print(f"  Inserted {len(SOURCES)} reference freshness rows")
        return len(SOURCES)
    finally:
        conn.close()


if __name__ == "__main__":
    run()
