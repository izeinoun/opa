"""seed_demo_cases.py — 15 focused demo cases with real detector execution.

Replaces seed_claims + seed_cases + seed_workflow.

Steps:
  1. DELETE all demo data (claims, cases, findings, ERA, audit trails)
  2. Mark provider 1111111114 as excluded (needed for DET-08)
  3. Insert 15 carefully designed claims / claim_lines
  4. Insert 15 opa_cases + likelihood_scores (placeholder values)
  5. Run all 6 detectors via DetectorService.run_for_case() — real findings
  6. Override dates, statuses, priority_score after detector output known
  7. Create audit trails and workflow records (ERA, notices)
  8. Print summary

Detector distribution:
  DET-04  : Cases  1, 4, 7, 10, 14, 15  (Fee Schedule overpayment)
  DET-01  : Cases  2, 5                  (Duplicate Billing pair)
  DET-06  : Cases  3, 11                 (NCCI/MUE Violation)
  DET-02  : Cases  6, 12                 (Cross-LOB Eligibility)
  DET-08  : Case   8                     (Excluded Provider)
  DET-09  : Cases  9, 13                 (Coding/DX-CPT Error)

All service dates are in 2024 (within fee schedule coverage 2024-01-01/2024-12-31).
All identified_dates are relative to TODAY at run time.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

# Ensure /server is on sys.path so app.* imports resolve
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.amount_at_risk import compute_at_risk_deduped  # noqa: E402

DB_PATH = os.getenv("DB_PATH", "./opa.db")
TODAY = date.today()

# ── CPT / ICD / likelihood helpers ────────────────────────────────────────

CPT_RISK = {
    "99213": 0.10, "99214": 0.20, "99215": 0.30, "99232": 0.35,
    "93000": 0.15, "93306": 0.40, "93458": 0.70, "27447": 0.65,
    "29881": 0.55, "97110": 0.25, "97530": 0.30, "70553": 0.35,
    "72148": 0.25, "99285": 0.45, "99291": 0.60,
}

PROVIDER_BV = {
    "1111111111": 0.72, "1111111112": 0.61, "1111111113": 0.38,
    "1111111114": 0.81, "2222222221": 0.29, "2222222222": 0.44,
    "2222222223": 0.18, "3333333331": 0.35, "3333333332": 0.15,
    "3333333333": 0.46,
}


def _composite(cpt: str, npi: str, n_lines: int) -> float:
    cr = CPT_RISK.get(cpt, 0.20)
    bv = PROVIDER_BV.get(npi, 0.30)
    return round(cr * 0.30 + bv * 0.25 + 0.15 * 0.20 + min(1.0, n_lines / 4) * 0.15 + bv * 0.10, 4)


def _priority_label(score: float, deadline: date) -> str:
    days = (deadline - TODAY).days
    if days <= 5:
        return "HIGH"
    if score >= 70:
        return "HIGH"
    if score >= 45:
        return "MEDIUM"
    return "LOW"


# ── Claim spec definitions ─────────────────────────────────────────────────
#
# Each entry drives one claim + one case.  All service dates are in 2024
# (within fee schedule range).  identified_date is set AFTER detector run.
#
# lob_override: if set, claim.lob differs from the member's enrolled LOB
#               (triggers DET-02).
#
# Fields used later:
#   seq              → case_sequence / ICN suffix
#   member_number    → looked up to member_id / member.lob
#   rendering_npi    → provider NPI
#   org_npi          → billing org NPI (→ provider_org_id)
#   lob_override     → claim LOB (if None, uses member.lob)
#   service_date     → 2024 date string
#   primary_icd      → claim primary ICD
#   lines            → list of line dicts
#   identified_days_ago → relative to TODAY
#   deadline_offset  → days from identified_date to deadline
#   status
#   priority
#   urgency          → urgency_factor in likelihood_score
#   urgency_override → bool (True for overdue cases)
#   analyst_idx      → index into analyst list (round-robin)
#   requires_sup     → requires_supervisor_approval
#   is_closed        → case is closed (is_active=False)

CLAIM_SPECS: list[dict] = [
    # ── CASES 1-3: identified 30 days ago, deadline 30 days from now ───────
    {
        "seq": 1, "detector": "DET-04",
        "member_number": "MA-000001", "rendering_npi": "1111111112", "org_npi": "9900000001",
        "service_date": "2024-04-15", "primary_icd": "M17.11",
        "lines": [
            {"cpt": "27447", "icd": ["M17.11"], "units": 1,
             "billed": 2362.50, "paid": 1968.75, "allowed": 1968.75},
        ],
        "identified_days_ago": 30, "deadline_offset": 60,
        "status": "in_review", "priority": "MEDIUM", "urgency": 0.50,
        "urgency_override": False, "analyst_idx": 0, "requires_sup": False, "is_closed": False,
    },
    {
        "seq": 2, "detector": "DET-01",
        "member_number": "MA-000002", "rendering_npi": "2222222222", "org_npi": "9900000002",
        "service_date": "2024-09-20", "primary_icd": "R07.9",
        "lines": [
            {"cpt": "99285", "icd": ["R07.9"], "units": 1,
             "billed": 280.00, "paid": 225.00, "allowed": 225.00},
        ],
        "identified_days_ago": 30, "deadline_offset": 60,
        "status": "in_review", "priority": "MEDIUM", "urgency": 0.50,
        "urgency_override": False, "analyst_idx": 1, "requires_sup": False, "is_closed": False,
    },
    {
        "seq": 3, "detector": "DET-06",
        "member_number": "MA-000003", "rendering_npi": "1111111112", "org_npi": "9900000001",
        "service_date": "2024-07-10", "primary_icd": "E11.9",
        "lines": [
            {"cpt": "97110", "icd": ["E11.9"], "units": 1,
             "billed": 50.40, "paid": 42.00, "allowed": 42.00},
            {"cpt": "97112", "icd": ["E11.9"], "units": 1,
             "billed": 57.60, "paid": 48.00, "allowed": 48.00},
        ],
        "identified_days_ago": 30, "deadline_offset": 60,
        "status": "in_review", "priority": "MEDIUM", "urgency": 0.50,
        "urgency_override": False, "analyst_idx": 2, "requires_sup": False, "is_closed": False,
    },
    # ── CASES 4-6: identified 45 days ago, deadline 15 days from now ───────
    {
        "seq": 4, "detector": "DET-04",
        "member_number": "PPO-000001", "rendering_npi": "3333333331", "org_npi": "9900000003",
        "service_date": "2024-05-20", "primary_icd": "M17.12",
        "lines": [
            {"cpt": "27447", "icd": ["M17.12"], "units": 1,
             "billed": 2650.00, "paid": 2212.50, "allowed": 2212.50},
        ],
        "identified_days_ago": 45, "deadline_offset": 60,
        "status": "in_review", "priority": "HIGH", "urgency": 0.75,
        "urgency_override": False, "analyst_idx": 3, "requires_sup": False, "is_closed": False,
    },
    {
        # Duplicate pair of case 2: same member, provider, service_date, CPT
        "seq": 5, "detector": "DET-01",
        "member_number": "MA-000002", "rendering_npi": "2222222222", "org_npi": "9900000002",
        "service_date": "2024-09-20", "primary_icd": "R07.9",  # IDENTICAL to case 2
        "lines": [
            {"cpt": "99285", "icd": ["R07.9"], "units": 1,
             "billed": 280.00, "paid": 225.00, "allowed": 225.00},
        ],
        "identified_days_ago": 45, "deadline_offset": 60,
        "status": "pending_supervisor", "priority": "HIGH", "urgency": 0.75,
        "urgency_override": False, "analyst_idx": 4, "requires_sup": True, "is_closed": False,
    },
    {
        # Cross-LOB: PPO-000002 is a PPO member billed under MA plan
        "seq": 6, "detector": "DET-02",
        "member_number": "PPO-000002", "rendering_npi": "3333333332", "org_npi": "9900000003",
        "lob_override": "MA",   # member.lob=PPO but claim filed as MA
        "service_date": "2024-08-05", "primary_icd": "I10",
        "lines": [
            {"cpt": "99213", "icd": ["I10"], "units": 1,
             "billed": 92.40, "paid": 77.00, "allowed": 77.00},
        ],
        "identified_days_ago": 45, "deadline_offset": 60,
        "status": "in_review", "priority": "HIGH", "urgency": 0.75,
        "urgency_override": False, "analyst_idx": 5, "requires_sup": False, "is_closed": False,
    },
    # ── CASES 7-9: identified 55 days ago, deadline 5 days from now ────────
    {
        "seq": 7, "detector": "DET-04",
        "member_number": "MA-000004", "rendering_npi": "1111111112", "org_npi": "9900000001",
        "service_date": "2024-06-10", "primary_icd": "M17.11",
        "lines": [
            {"cpt": "27447", "icd": ["M17.11"], "units": 1,
             "billed": 2362.50, "paid": 1968.75, "allowed": 1968.75},
        ],
        "identified_days_ago": 55, "deadline_offset": 60,
        "status": "notice_sent", "priority": "HIGH", "urgency": 0.90,
        "urgency_override": False, "analyst_idx": 0, "requires_sup": False, "is_closed": False,
    },
    {
        # Excluded provider — NPI 1111111114 will be marked excluded
        "seq": 8, "detector": "DET-08",
        "member_number": "MA-000005", "rendering_npi": "1111111114", "org_npi": "9900000001",
        "service_date": "2024-05-01", "primary_icd": "I10",
        "lines": [
            {"cpt": "99214", "icd": ["I10"], "units": 1,
             "billed": 138.00, "paid": 115.00, "allowed": 115.00},
        ],
        "identified_days_ago": 55, "deadline_offset": 60,
        "status": "in_review", "priority": "HIGH", "urgency": 0.90,
        "urgency_override": False, "analyst_idx": 1, "requires_sup": False, "is_closed": False,
    },
    {
        # DX/CPT mismatch: M17.11 (right knee OA) + 93458 (left heart cath)
        "seq": 9, "detector": "DET-09",
        "member_number": "MA-000006", "rendering_npi": "2222222222", "org_npi": "9900000002",
        "service_date": "2024-10-15", "primary_icd": "M17.11",
        "lines": [
            {"cpt": "93458", "icd": ["M17.11"], "units": 1,
             "billed": 1650.00, "paid": 1386.00, "allowed": 1386.00},
        ],
        "identified_days_ago": 55, "deadline_offset": 60,
        "status": "in_review", "priority": "HIGH", "urgency": 0.90,
        "urgency_override": False, "analyst_idx": 2, "requires_sup": False, "is_closed": False,
    },
    # ── CASES 10-12: identified 62 days ago, OVERDUE (deadline 2 days ago) ─
    {
        "seq": 10, "detector": "DET-04",
        "member_number": "MA-000007", "rendering_npi": "3333333331", "org_npi": "9900000003",
        "service_date": "2024-07-15", "primary_icd": "M17.11",
        "lines": [
            {"cpt": "27447", "icd": ["M17.11"], "units": 1,
             "billed": 2362.50, "paid": 1968.75, "allowed": 1968.75},
        ],
        "identified_days_ago": 62, "deadline_offset": 60,  # 60-62 = -2 → overdue
        "status": "in_review", "priority": "HIGH", "urgency": 1.00,
        "urgency_override": True, "analyst_idx": 3, "requires_sup": False, "is_closed": False,
    },
    {
        # NCCI pair: 97110 + 97112 on same PPO claim — overdue
        "seq": 11, "detector": "DET-06",
        "member_number": "PPO-000003", "rendering_npi": "2222222221", "org_npi": "9900000002",
        "service_date": "2024-11-05", "primary_icd": "I25.10",
        "lines": [
            {"cpt": "97110", "icd": ["I25.10"], "units": 1,
             "billed": 56.40, "paid": 47.04, "allowed": 47.04},
            {"cpt": "97112", "icd": ["I25.10"], "units": 1,
             "billed": 62.40, "paid": 52.00, "allowed": 52.00},
        ],
        "identified_days_ago": 62, "deadline_offset": 60,
        "status": "assigned", "priority": "HIGH", "urgency": 1.00,
        "urgency_override": True, "analyst_idx": 4, "requires_sup": False, "is_closed": False,
    },
    {
        # Cross-LOB: MA-000008 is an MA member billed under PPO plan — overdue
        "seq": 12, "detector": "DET-02",
        "member_number": "MA-000008", "rendering_npi": "3333333333", "org_npi": "9900000003",
        "lob_override": "PPO",  # member.lob=MA but claim filed as PPO
        "service_date": "2024-09-10", "primary_icd": "E11.9",
        "lines": [
            {"cpt": "99214", "icd": ["E11.9"], "units": 1,
             "billed": 154.56, "paid": 128.80, "allowed": 128.80},
        ],
        "identified_days_ago": 62, "deadline_offset": 60,
        "status": "in_review", "priority": "HIGH", "urgency": 1.00,
        "urgency_override": True, "analyst_idx": 5, "requires_sup": False, "is_closed": False,
    },
    # ── CASE 13: new, low priority, plenty of time ─────────────────────────
    {
        # Absurd coding error: migraine patient billed for knee replacement
        "seq": 13, "detector": "DET-09",
        "member_number": "PPO-000004", "rendering_npi": "1111111113", "org_npi": "9900000001",
        "service_date": "2024-12-20", "primary_icd": "G43.909",
        "lines": [
            {"cpt": "27447", "icd": ["G43.909"], "units": 1,
             "billed": 2124.00, "paid": 1770.00, "allowed": 1770.00},
        ],
        "identified_days_ago": 10, "deadline_offset": 90,  # deadline July 4
        "status": "new", "priority": "LOW", "urgency": 0.30,
        "urgency_override": False, "analyst_idx": 0, "requires_sup": False, "is_closed": False,
    },
    # ── CASE 14: closed_recovered, 90 days ago ──────────────────────────────
    {
        "seq": 14, "detector": "DET-04",
        "member_number": "PPO-000005", "rendering_npi": "3333333331", "org_npi": "9900000003",
        "service_date": "2024-01-15", "primary_icd": "M17.11",
        "lines": [
            {"cpt": "27447", "icd": ["M17.11"], "units": 1,
             "billed": 2650.00, "paid": 2212.50, "allowed": 2212.50},
        ],
        "identified_days_ago": 90, "deadline_offset": 60,
        "status": "closed_recovered", "priority": "MEDIUM", "urgency": 0.85,
        "urgency_override": False, "analyst_idx": 1, "requires_sup": False, "is_closed": True,
    },
    # ── CASE 15: pending_supervisor, high-dollar, requires approval ─────────
    {
        # Fee schedule fraud: PPO knee replacement billed at 5× the contracted rate
        "seq": 15, "detector": "DET-04",
        "member_number": "PPO-000006", "rendering_npi": "1111111111", "org_npi": "9900000001",
        "service_date": "2024-03-10", "primary_icd": "M17.11",
        "lines": [
            {"cpt": "27447", "icd": ["M17.11"], "units": 1,
             "billed": 11625.00, "paid": 9300.00, "allowed": 9300.00},
        ],
        "identified_days_ago": 30, "deadline_offset": 60,
        "status": "pending_supervisor", "priority": "HIGH", "urgency": 0.60,
        "urgency_override": False, "analyst_idx": 2, "requires_sup": True, "is_closed": False,
    },
    # ── CASE 16: multi-line DET-04 ────────────────────────────────────────
    # Orthopedic follow-up + PT bundle. 5 lines, 3 violate fee schedule, 2 clean.
    # Demonstrates the per-line evidence table when DET-04 fires on multiple lines.
    {
        "seq": 16, "detector": "DET-04",
        "member_number": "PPO-000007", "rendering_npi": "1111111111", "org_npi": "9900000001",
        "service_date": "2024-08-15", "primary_icd": "M17.11",
        "lines": [
            # 99214 PPO highest tier ~135.70 → paid 165 = +22% (FIRES)
            {"cpt": "99214", "icd": ["M17.11"], "units": 1,
             "billed": 198.00, "paid": 165.00, "allowed": 165.00},
            # 97110 PPO highest tier  49.56 → paid 49  = under tolerance (CLEAN)
            {"cpt": "97110", "icd": ["M17.11"], "units": 1,
             "billed":  58.80, "paid":  49.00, "allowed":  49.00},
            # 97530 PPO highest tier  56.64 → paid 95  = +68% (FIRES)
            {"cpt": "97530", "icd": ["M17.11"], "units": 1,
             "billed": 114.00, "paid":  95.00, "allowed":  95.00},
            # 99213 PPO highest tier  90.86 → paid 90  = under tolerance (CLEAN)
            {"cpt": "99213", "icd": ["M17.11"], "units": 1,
             "billed": 108.00, "paid":  90.00, "allowed":  90.00},
            # 99215 PPO highest tier 182.90 → paid 220 = +20% (FIRES)
            {"cpt": "99215", "icd": ["M17.11"], "units": 1,
             "billed": 264.00, "paid": 220.00, "allowed": 220.00},
        ],
        "identified_days_ago": 20, "deadline_offset": 60,
        "status": "in_review", "priority": "HIGH", "urgency": 0.50,
        "urgency_override": False, "analyst_idx": 3, "requires_sup": False, "is_closed": False,
    },
    # ── CASES 17-19: BATCHED ERA ──────────────────────────────────────────
    # Three independent PPO claims billed by the same provider org on the same
    # remittance cycle. They share `era_batch="BATCH-2024-A"` so they all
    # collapse into ONE transactions_835 with 3 distinct CLP rows — the
    # canonical "weekly batch remittance" pattern.
    {
        "seq": 17, "detector": "DET-04",
        "member_number": "PPO-000008", "rendering_npi": "1111111111", "org_npi": "9900000001",
        "service_date": "2024-08-22", "primary_icd": "M17.11",
        "lines": [
            # 29881 PPO highest tier 991.20 → paid 1100 = +11% (FIRES)
            {"cpt": "29881", "icd": ["M17.11"], "units": 1,
             "billed": 1320.00, "paid": 1100.00, "allowed": 1100.00},
        ],
        "identified_days_ago": 20, "deadline_offset": 60,
        "status": "in_review", "priority": "MEDIUM", "urgency": 0.50,
        "urgency_override": False, "analyst_idx": 4, "requires_sup": False, "is_closed": False,
        "era_batch": "BATCH-2024-A",
    },
    {
        # NCCI mutually-exclusive pair on a single claim — 97110 + 97112
        "seq": 18, "detector": "DET-06",
        "member_number": "PPO-000009", "rendering_npi": "1111111111", "org_npi": "9900000001",
        "service_date": "2024-08-22", "primary_icd": "I25.10",
        "lines": [
            {"cpt": "97110", "icd": ["I25.10"], "units": 1,
             "billed":  58.80, "paid":  49.00, "allowed":  49.00},
            {"cpt": "97112", "icd": ["I25.10"], "units": 1,
             "billed":  62.40, "paid":  52.00, "allowed":  52.00},
        ],
        "identified_days_ago": 20, "deadline_offset": 60,
        "status": "in_review", "priority": "MEDIUM", "urgency": 0.50,
        "urgency_override": False, "analyst_idx": 5, "requires_sup": False, "is_closed": False,
        "era_batch": "BATCH-2024-A",
    },
    {
        "seq": 19, "detector": "DET-04",
        "member_number": "PPO-000010", "rendering_npi": "1111111111", "org_npi": "9900000001",
        "service_date": "2024-08-22", "primary_icd": "M17.11",
        "lines": [
            # 99214 PPO highest tier 135.70 → paid 145 = +7% (just over tolerance, FIRES)
            {"cpt": "99214", "icd": ["M17.11"], "units": 1,
             "billed": 175.00, "paid": 145.00, "allowed": 145.00},
        ],
        "identified_days_ago": 20, "deadline_offset": 60,
        "status": "in_review", "priority": "LOW", "urgency": 0.30,
        "urgency_override": False, "analyst_idx": 0, "requires_sup": False, "is_closed": False,
        "era_batch": "BATCH-2024-A",
    },
]


# ── Reference data helpers ─────────────────────────────────────────────────

def _load_refs(conn: sqlite3.Connection) -> dict:
    members = {
        row[0]: {"uuid": row[1], "lob": row[2]}
        for row in conn.execute("SELECT member_number, member_id, lob FROM members").fetchall()
    }
    orgs = {
        row[0]: row[1]
        for row in conn.execute("SELECT npi, provider_org_id FROM provider_orgs").fetchall()
    }
    analysts = [
        row[0]
        for row in conn.execute(
            "SELECT user_id FROM opa_users WHERE role='analyst' ORDER BY username"
        ).fetchall()
    ]
    supervisors = [
        row[0]
        for row in conn.execute(
            "SELECT user_id FROM opa_users WHERE role='supervisor' ORDER BY username"
        ).fetchall()
    ]
    system_user = conn.execute(
        "SELECT user_id FROM opa_users WHERE role='system' LIMIT 1"
    ).fetchone()
    system_id = system_user[0] if system_user else (analysts[0] if analysts else None)
    return {"members": members, "orgs": orgs, "analysts": analysts,
            "supervisors": supervisors, "system_id": system_id}


# ── Demo data clearing ─────────────────────────────────────────────────────

def _clear_demo_data(conn: sqlite3.Connection) -> None:
    tables = [
        "reconciliations",
        "recoupment_actions",
        "provider_notices",
        "disputes",
        "audit_logs",
        "likelihood_scores",
        "case_findings",
        "opa_cases",
        "findings",
        "claim_lines",
        "claim_headers_837",
        "claim_payments_835",
        "transactions_835",
        "claims",
        "case_groups",
    ]
    for t in tables:
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            if n:
                conn.execute(f"DELETE FROM {t}")
                print(f"    Cleared {n:,} rows from {t}")
        except sqlite3.OperationalError as exc:
            print(f"    Skip {t}: {exc}")
    conn.commit()


# ── Claim / case insertion ─────────────────────────────────────────────────

def _icn(seq: int) -> str:
    return f"CLM-2026-{seq:05d}"


def _case_number(seq: int) -> str:
    return f"OPA-2026-{seq:05d}"


def _insert_claims(conn: sqlite3.Connection, refs: dict) -> list[dict]:
    """Insert all claims + lines from CLAIM_SPECS; return per-case metadata dicts."""
    results = []
    NOW = datetime.now().isoformat()

    for spec in CLAIM_SPECS:
        member = refs["members"][spec["member_number"]]
        lob = spec.get("lob_override") or member["lob"]
        org_id = refs["orgs"][spec["org_npi"]]
        claim_id = str(uuid4())
        icn = _icn(spec["seq"])
        svc = spec["service_date"]
        svc_date = date.fromisoformat(svc)
        paid_date = (svc_date + timedelta(days=20)).isoformat()
        submit_date = (svc_date + timedelta(days=14)).isoformat()

        total_billed = round(sum(ln["billed"] for ln in spec["lines"]), 2)
        total_paid = round(sum(ln["paid"] for ln in spec["lines"]), 2)

        conn.execute(
            "INSERT INTO claims "
            "(claim_id, icn, case_group_id, member_id, provider_org_id, "
            "billing_provider_npi, rendering_provider_npi, lob, "
            "service_from_date, service_to_date, claim_type, claim_status, "
            "total_billed, total_paid, paid_date, authorization_number, "
            "submission_date, pos_code, primary_icd, era_transaction_id, "
            "raw_claim_json, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                claim_id, icn, None, member["uuid"], org_id,
                spec["rendering_npi"], spec["rendering_npi"], lob,
                svc, svc, "professional", "paid",
                total_billed, total_paid, paid_date, None,
                submit_date, "11", spec["primary_icd"], None,
                json.dumps({"icn": icn}), NOW, NOW,
            ),
        )

        for i, ln in enumerate(spec["lines"], 1):
            conn.execute(
                "INSERT INTO claim_lines "
                "(claim_line_id, claim_id, line_number, cpt_code, icd_codes, "
                "modifier_1, modifier_2, units_billed, units_paid, "
                "billed_amount, paid_amount, allowed_amount, pos_code, revenue_code) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()), claim_id, i, ln["cpt"],
                    json.dumps(ln["icd"]),
                    None, None, ln["units"], ln["units"],
                    ln["billed"], ln["paid"], ln["allowed"],
                    "11", None,
                ),
            )

        results.append({
            "seq": spec["seq"],
            "claim_id": claim_id,
            "icn": icn,
            "lob": lob,
            "member_uuid": member["uuid"],
            "org_id": org_id,
            "rendering_npi": spec["rendering_npi"],
            "org_npi": spec["org_npi"],
            "total_paid": total_paid,
            "primary_cpt": spec["lines"][0]["cpt"],
            "spec": spec,
        })

    conn.commit()
    print(f"    Inserted {len(results)} claims")
    return results


def _insert_cases(conn: sqlite3.Connection, claim_data: list[dict], refs: dict) -> list[int]:
    NOW = datetime.now().isoformat()
    case_ids: dict[int, str] = {}

    for cd in claim_data:
        spec = cd["spec"]
        case_id = str(uuid4())
        seq = spec["seq"]
        case_ids[seq] = case_id

        identified_date = TODAY - timedelta(days=spec["identified_days_ago"])
        deadline_date = identified_date + timedelta(days=spec["deadline_offset"])
        breached = int(deadline_date < TODAY)
        is_active = int(not spec["is_closed"])

        analyst_id = refs["analysts"][spec["analyst_idx"] % len(refs["analysts"])]
        cpt = cd["primary_cpt"]
        npi = cd["rendering_npi"]
        n_lines = len(spec["lines"])
        composite = _composite(cpt, npi, n_lines)

        amount_norm = min(1.0, cd["total_paid"] / 2000.0)
        urgency = spec["urgency"]
        priority_score = round((amount_norm * 0.40 + composite * 0.40 + urgency * 0.20) * 100, 2)
        priority = spec["priority"]

        lookback_start = (date.fromisoformat(spec["service_date"]) - timedelta(days=365)).isoformat()

        recovery_method = "offset" if cd["total_paid"] >= 500 and cd["lob"] != "Medicaid" else "invoice"

        approx_overpayment = round(cd["total_paid"] * 0.25, 2)  # placeholder, updated after detector run

        conn.execute(
            "INSERT INTO opa_cases "
            "(case_id, case_number, case_sequence, claim_id, case_group_id, "
            "primary_detector_id, lob, provider_org_id, member_id, "
            "assigned_analyst_id, status, is_active, priority, priority_score, "
            "total_overpayment_amount, recommended_recovery_method, "
            "identified_date, deadline_date, deadline_breached, "
            "lookback_window_start, provider_response_due_date, "
            "is_sensitive_provider, requires_supervisor_approval, "
            "evidence_bundle, case_json, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                case_id, _case_number(seq), seq, cd["claim_id"], None,
                spec["detector"], cd["lob"], cd["org_id"], cd["member_uuid"],
                analyst_id, spec["status"], is_active, priority, priority_score,
                approx_overpayment, recovery_method,
                identified_date.isoformat(), deadline_date.isoformat(), breached,
                lookback_start,
                (identified_date + timedelta(days=30)).isoformat(),
                0, int(spec["requires_sup"]),
                json.dumps({"detector": spec["detector"], "cpt": cpt}),
                json.dumps({"seq": seq}),
                NOW, NOW,
            ),
        )

        conn.execute(
            "INSERT INTO likelihood_scores "
            "(score_id, case_id, provider_risk_score, cpt_risk_score, "
            "dx_cpt_mismatch_score, claim_complexity_score, billing_variance_score, "
            "composite_likelihood, urgency_factor, urgency_override_applied, "
            "priority_score, score_json, scored_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(uuid4()), case_id,
                PROVIDER_BV.get(npi, 0.30),
                CPT_RISK.get(cpt, 0.20),
                0.15,
                min(1.0, n_lines / 4.0),
                PROVIDER_BV.get(npi, 0.30),
                composite,
                urgency,
                int(spec["urgency_override"]),
                priority_score,
                json.dumps({"composite": composite}),
                NOW,
            ),
        )

    conn.commit()
    print(f"    Inserted {len(claim_data)} cases + likelihood_scores")
    return case_ids


# ── Async detector execution ───────────────────────────────────────────────

async def _run_detectors_async(case_sequences: list[int], db_path: str) -> dict[int, dict]:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.services.detector_service import DetectorService

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    AsyncSessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    results: dict[int, dict] = {}
    async with AsyncSessionFactory() as session:
        for seq in case_sequences:
            try:
                svc = DetectorService(session)
                res = await svc.run_for_case(seq)
                results[seq] = res
                fired = len(res["findings"])
                total_overpay = sum(f["overpayment"] for f in res["findings"])
                print(f"    Case {seq:2d}: {fired} finding(s)  "
                      f"total overpayment ${total_overpay:,.2f}")
            except Exception as exc:
                print(f"    Case {seq:2d}: detector error — {exc}")
                results[seq] = {"findings": []}

    await engine.dispose()
    return results


# ── Post-detector updates ──────────────────────────────────────────────────

def _update_case_overpayments(
    conn: sqlite3.Connection, detector_results: dict[int, dict]
) -> None:
    NOW = datetime.now().isoformat()
    for seq, res in detector_results.items():
        if not res.get("findings"):
            # Detector didn't fire — keep placeholder estimate
            continue

        row = conn.execute(
            "SELECT claim_id FROM opa_cases WHERE case_sequence=?", (seq,)
        ).fetchone()
        if not row:
            continue
        claim_id = row[0]

        line_rows = conn.execute(
            "SELECT claim_line_id, claim_id, cpt_code, paid_amount "
            "FROM claim_lines WHERE claim_id=?", (claim_id,)
        ).fetchall()
        claim_lines = [
            SimpleNamespace(claim_line_id=r[0], claim_id=r[1], cpt_code=r[2], paid_amount=r[3])
            for r in line_rows
        ]

        finding_rows = conn.execute(
            "SELECT finding_id, claim_id, claim_line_id, detector_id, "
            "overpayment_amount, evidence FROM findings WHERE claim_id=?", (claim_id,)
        ).fetchall()
        findings = [
            SimpleNamespace(
                finding_id=r[0], claim_id=r[1], claim_line_id=r[2],
                detector_id=r[3], overpayment_amount=r[4], evidence=r[5],
            )
            for r in finding_rows
        ]

        deduped_total, _ = compute_at_risk_deduped(claim_lines, findings)
        conn.execute(
            "UPDATE opa_cases SET total_overpayment_amount=?, updated_at=? "
            "WHERE case_sequence=?",
            (round(deduped_total, 2), NOW, seq),
        )

    # For case 15 override: if DET-04 found < $5K, force the amount
    # (demonstrates high-dollar supervisor case)
    row = conn.execute(
        "SELECT total_overpayment_amount FROM opa_cases WHERE case_sequence=15"
    ).fetchone()
    if row and row[0] < 5000:
        conn.execute(
            "UPDATE opa_cases SET total_overpayment_amount=? WHERE case_sequence=15",
            (max(row[0], 7530.00),),
        )

    conn.commit()


def _update_priority_scores(conn: sqlite3.Connection) -> None:
    """Recompute priority_score from updated likelihood + urgency after detector run."""
    rows = conn.execute(
        "SELECT c.case_sequence, c.total_overpayment_amount, "
        "ls.composite_likelihood, ls.urgency_factor "
        "FROM opa_cases c JOIN likelihood_scores ls ON c.case_id = ls.case_id"
    ).fetchall()
    NOW = datetime.now().isoformat()
    for seq, amount, composite, urgency in rows:
        amount_norm = min(1.0, float(amount) / 50000.0)
        score = round((amount_norm * 0.40 + float(composite) * 0.40 + float(urgency) * 0.20) * 100, 2)
        conn.execute(
            "UPDATE opa_cases SET priority_score=?, updated_at=? WHERE case_sequence=?",
            (score, NOW, seq),
        )
    conn.commit()


# ── Audit trail creation ───────────────────────────────────────────────────

_STATUS_TRANSITIONS = {
    "new": [],
    "assigned": [
        ("new", "assigned", "CASE_ASSIGNED", 2),
    ],
    "in_review": [
        ("new", "assigned", "CASE_ASSIGNED", 2),
        ("assigned", "in_review", "STATUS_TRANSITION", 4),
    ],
    "pending_supervisor": [
        ("new", "assigned", "CASE_ASSIGNED", 2),
        ("assigned", "in_review", "STATUS_TRANSITION", 4),
        ("in_review", "pending_supervisor", "STATUS_TRANSITION", 7),
    ],
    "notice_sent": [
        ("new", "assigned", "CASE_ASSIGNED", 2),
        ("assigned", "in_review", "STATUS_TRANSITION", 4),
        ("in_review", "notice_sent", "STATUS_TRANSITION", 10),
    ],
    "closed_recovered": [
        ("new", "assigned", "CASE_ASSIGNED", 2),
        ("assigned", "in_review", "STATUS_TRANSITION", 4),
        ("in_review", "notice_sent", "STATUS_TRANSITION", 10),
        ("notice_sent", "provider_responded", "STATUS_TRANSITION", 25),
        ("provider_responded", "reconciling", "STATUS_TRANSITION", 50),
        ("reconciling", "closed_recovered", "STATUS_TRANSITION", 70),
    ],
}


def _create_audit_trails(
    conn: sqlite3.Connection, claim_data: list[dict], refs: dict
) -> None:
    NOW = datetime.now().isoformat()
    system_id = refs["system_id"]

    for cd in claim_data:
        spec = cd["spec"]
        # Look up case_id
        row = conn.execute(
            "SELECT case_id, identified_date, assigned_analyst_id "
            "FROM opa_cases WHERE case_sequence=?",
            (spec["seq"],),
        ).fetchone()
        if not row:
            continue
        case_id, identified_date_str, analyst_id = row
        identified_date = date.fromisoformat(identified_date_str)

        # CASE_CREATED is always first
        created_ts = datetime.combine(identified_date, datetime.min.time()).replace(hour=8).isoformat()
        conn.execute(
            "INSERT INTO audit_logs "
            "(audit_id, case_id, actor_user_id, action, from_state, to_state, reason, meta_json, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (str(uuid4()), case_id, system_id, "CASE_CREATED", None, "new",
             "Overpayment identified by automated detector run", "{}", created_ts),
        )

        transitions = _STATUS_TRANSITIONS.get(spec["status"], [])
        for from_s, to_s, action, offset_days in transitions:
            ts = datetime.combine(
                identified_date + timedelta(days=offset_days), datetime.min.time()
            ).replace(hour=9).isoformat()
            actor = analyst_id if to_s != "new" else system_id
            conn.execute(
                "INSERT INTO audit_logs "
                "(audit_id, case_id, actor_user_id, action, from_state, to_state, reason, meta_json, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (str(uuid4()), case_id, actor, action, from_s, to_s,
                 f"Status updated to {to_s}", "{}", ts),
            )

    conn.commit()
    print(f"    Audit trails created for {len(claim_data)} cases")


# ── 835 ERA payments ──────────────────────────────────────────────────────

_PAYER = {
    "MA":       "CMS Medicare Advantage",
    "PPO":      "UnitedHealth Group PPO",
    "Medicaid": "State DHHS Medicaid",
}

# CAS reason codes to use per detector
# DET-04: CO-45  — charges exceed contracted fee schedule (payer reduced but not enough)
# DET-01: PR-2   — patient coinsurance only; both claims paid, no CO-97 rejection
# DET-06: PR-2   — both NCCI codes fully paid; no bundling edit applied
# DET-02: PR-2   — wrong-plan payment; cross-LOB not detected at adjudication
# DET-08: PR-2   — full payment to excluded provider; no CO-109 applied
# DET-09: PR-2   — coding error paid through; no clinical editing triggered
_ADJ_CODE: dict[str, str] = {
    "DET-04": "CO-45",
    "DET-01": "PR-2",
    "DET-06": "PR-2",
    "DET-02": "PR-2",
    "DET-08": "PR-2",
    "DET-09": "PR-2",
}


def _create_all_eras(conn: sqlite3.Connection, claim_data: list[dict]) -> None:
    """Create payment ERAs and link them to claims.

    Claims with a shared `era_batch` value collapse into ONE transactions_835
    row containing N distinct CLP claim_payments_835 rows (one CLP per line of
    each claim). Claims without an `era_batch` get their own solo ERA, 1:1.
    """
    NOW = datetime.now().isoformat()

    # Bucket claims by their era_batch key; ungrouped get a unique solo key.
    batches: dict[str, list[dict]] = {}
    for cd in claim_data:
        key = cd["spec"].get("era_batch") or f"__solo__{cd['spec']['seq']}"
        batches.setdefault(key, []).append(cd)

    txn_count = 0
    for batch_key, cds in batches.items():
        is_batch = not batch_key.startswith("__solo__")
        primary = cds[0]
        primary_spec = primary["spec"]
        # Payment date = service date of primary claim + 20 days; all batched
        # claims share this date in the demo (real payers send one batch on one date).
        svc_date = date.fromisoformat(primary_spec["service_date"])
        payment_date = (svc_date + timedelta(days=20)).isoformat()
        payer = _PAYER.get(primary["lob"], "CMS Medicare Advantage")

        # Gather lines for every claim in the batch.
        all_lines: list[tuple] = []  # (cd, line_id, cpt, billed, paid)
        for cd in cds:
            for ln in conn.execute(
                "SELECT claim_line_id, cpt_code, billed_amount, paid_amount FROM claim_lines "
                "WHERE claim_id=? ORDER BY line_number",
                (cd["claim_id"],),
            ).fetchall():
                all_lines.append((cd, *ln))

        total_amount = round(sum(p for _, _, _, _, p in all_lines), 2)

        txn_id = str(uuid4())
        if is_batch:
            era_num = f"ERA-2024-{primary['lob'][:3].upper()}-{batch_key}"
            check_num = f"CHK-2024-{batch_key}"
            note = {
                "batch": batch_key,
                "claim_icns": [cd["icn"] for cd in cds],
                "claim_count": len(cds),
            }
        else:
            era_num = f"ERA-2024-{primary['lob'][:3].upper()}-{primary_spec['seq']:05d}"
            check_num = f"CHK-2024-{primary_spec['seq']:05d}"
            note = {
                "icn": primary["icn"],
                "detector_note": f"{primary_spec['detector']} finding expected",
            }

        conn.execute(
            "INSERT INTO transactions_835 "
            "(transaction_id, transaction_number, transaction_type, payer_name, "
            "provider_org_id, transaction_date, total_amount, claim_count, "
            "raw_835_json, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                txn_id, era_num, "payment", payer,
                primary["org_id"], payment_date, total_amount, len(cds),
                json.dumps(note), NOW,
            ),
        )

        for cd, _line_id, cpt, billed, paid in all_lines:
            adj_amt = round(billed - paid, 2)
            adj_code = _ADJ_CODE.get(cd["spec"]["detector"], "PR-2")
            code = adj_code if adj_amt > 0 else None
            conn.execute(
                "INSERT INTO claim_payments_835 "
                "(payment_id, transaction_id, claim_icn, cpt_code, "
                "paid_amount, adjustment_amount, adjustment_reason_code, "
                "check_number, payment_date) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()), txn_id, cd["icn"], cpt,
                    paid, adj_amt, code,
                    check_num, payment_date,
                ),
            )

        # Link every claim in the batch to this shared ERA.
        for cd in cds:
            conn.execute(
                "UPDATE claims SET era_transaction_id=? WHERE claim_id=?",
                (txn_id, cd["claim_id"]),
            )

        txn_count += 1

    conn.commit()
    print(f"    Created {txn_count} ERA payment transactions ({len(claim_data)} claims linked)")


# ── ERA / Recovery notice for case 14 (closed_recovered) ──────────────────

def _notice_insert(
    conn: sqlite3.Connection,
    case_id: str,
    lob: str,
    overpay: float,
    notice_date: str,
    status: str,
    NOW: str,
) -> None:
    tmpl_id = {"MA": "TMPL-MA-001", "PPO": "TMPL-PPO-001"}.get(lob, "TMPL-MA-001")
    content = json.dumps({
        "amount_demanded": float(overpay),
        "response_due": (date.fromisoformat(notice_date) + timedelta(days=30)).isoformat(),
        "delivery_method": "certified_mail",
    })
    conn.execute(
        "INSERT INTO provider_notices "
        "(notice_id, case_id, template_id, lob, generated_at, letter_content, "
        "status, sent_at, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            str(uuid4()), case_id, tmpl_id, lob,
            notice_date, content, status,
            notice_date if status in ("sent", "recovered") else None,
            NOW, NOW,
        ),
    )


def _create_era_for_case14(conn: sqlite3.Connection, claim_data: list[dict]) -> None:
    cd14 = next((cd for cd in claim_data if cd["seq"] == 14), None)
    if not cd14:
        return

    identified_date = date.fromisoformat(
        conn.execute(
            "SELECT identified_date FROM opa_cases WHERE case_sequence=14"
        ).fetchone()[0]
    )
    recovery_date = TODAY - timedelta(days=20)
    NOW = datetime.now().isoformat()

    # ERA 835 reversal transaction
    txn_id = str(uuid4())
    pay_id = str(uuid4())
    conn.execute(
        "INSERT INTO transactions_835 "
        "(transaction_id, transaction_number, transaction_type, payer_name, "
        "provider_org_id, transaction_date, total_amount, claim_count, "
        "raw_835_json, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            txn_id, "ERA-2026-RCVR-00014", "recovery",
            "CMS Medicare Advantage" if cd14["lob"] == "MA" else "UnitedHealth PPO",
            cd14["org_id"],
            recovery_date.isoformat(),
            -cd14["total_paid"], 1,
            json.dumps({"recovery": True, "icn": cd14["icn"]}),
            NOW,
        ),
    )
    conn.execute(
        "INSERT INTO claim_payments_835 "
        "(payment_id, transaction_id, claim_icn, cpt_code, "
        "paid_amount, adjustment_amount, adjustment_reason_code, "
        "check_number, payment_date) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            pay_id, txn_id, cd14["icn"], cd14["primary_cpt"],
            -cd14["total_paid"],
            cd14["total_paid"],
            "45",           # PR-45 charges exceed fee schedule
            "CHK-RCVR-0014",
            recovery_date.isoformat(),
        ),
    )
    # Link claim → ERA
    conn.execute(
        "UPDATE claims SET era_transaction_id=? WHERE claim_id=?",
        (txn_id, cd14["claim_id"]),
    )

    # Provider notice for case 14
    case_row = conn.execute(
        "SELECT case_id, total_overpayment_amount FROM opa_cases WHERE case_sequence=14"
    ).fetchone()
    if case_row:
        case_id_14, overpay = case_row
        notice_date = (identified_date + timedelta(days=10)).isoformat()
        _notice_insert(conn, case_id_14, cd14["lob"], overpay, notice_date, "recovered", NOW)

    conn.commit()
    print("    ERA reversal + notice created for case 14")


def _create_notice_for_case7(conn: sqlite3.Connection, claim_data: list[dict]) -> None:
    cd7 = next((cd for cd in claim_data if cd["seq"] == 7), None)
    case_row = conn.execute(
        "SELECT case_id, identified_date, total_overpayment_amount "
        "FROM opa_cases WHERE case_sequence=7"
    ).fetchone()
    if not case_row or not cd7:
        return
    case_id, identified_date_str, overpay = case_row
    identified_date = date.fromisoformat(identified_date_str)
    notice_date = (identified_date + timedelta(days=10)).isoformat()
    NOW = datetime.now().isoformat()
    _notice_insert(conn, case_id, cd7["lob"], overpay, notice_date, "sent", NOW)
    conn.commit()
    print("    Recovery notice created for case 7")


# ── Summary ────────────────────────────────────────────────────────────────

def _print_summary(conn: sqlite3.Connection, detector_results: dict) -> None:
    overdue = conn.execute(
        "SELECT COUNT(*) FROM opa_cases WHERE deadline_breached=1 AND is_active=1"
    ).fetchone()[0]
    due7 = conn.execute(
        f"SELECT COUNT(*) FROM opa_cases WHERE deadline_date <= '{(TODAY + timedelta(days=7)).isoformat()}' "
        f"AND deadline_date >= '{TODAY.isoformat()}' AND is_active=1"
    ).fetchone()[0]
    due30 = conn.execute(
        f"SELECT COUNT(*) FROM opa_cases WHERE deadline_date <= '{(TODAY + timedelta(days=30)).isoformat()}' "
        f"AND deadline_date > '{(TODAY + timedelta(days=7)).isoformat()}' AND is_active=1"
    ).fetchone()[0]

    total_findings = sum(len(r.get("findings", [])) for r in detector_results.values())
    det_runs = len(detector_results) * 6

    earliest = conn.execute("SELECT MIN(identified_date) FROM opa_cases").fetchone()[0]
    latest = conn.execute("SELECT MAX(identified_date) FROM opa_cases").fetchone()[0]

    claims_n = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    cases_n = conn.execute("SELECT COUNT(*) FROM opa_cases").fetchone()[0]
    findings_n = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    audit_n = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    era_n = conn.execute("SELECT COUNT(*) FROM transactions_835").fetchone()[0]
    era_lines_n = conn.execute("SELECT COUNT(*) FROM claim_payments_835").fetchone()[0]

    print(f"\n{'─' * 55}")
    print("Demo seed summary")
    print(f"{'─' * 55}")
    print(f"  Demo cases created        : {cases_n}")
    print(f"  Claims created            : {claims_n}")
    print(f"  Detectors run             : {det_runs} ({len(detector_results)} claims × 6)")
    print(f"  Findings generated        : {findings_n} (real detector output)")
    print(f"  ERA transactions          : {era_n} ({era_lines_n} payment lines)")
    print(f"  Audit log entries         : {audit_n}")
    print(f"  Date range                : {earliest} → {latest}")
    print(f"  Overdue cases             : {overdue}")
    print(f"  Due within 7 days         : {due7}")
    print(f"  Due within 8-30 days      : {due30}")
    print(f"  Training data             : 5,000 rows (separate CSV, ML only)")


# ── Main entry point ───────────────────────────────────────────────────────

def run(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")

    print("  Step 1/8 — clearing demo data")
    _clear_demo_data(conn)

    print("  Step 2/8 — marking provider 1111111114 as excluded (DET-08)")
    conn.execute(
        "UPDATE providers SET is_excluded=1, exclusion_source='OIG SAM Exclusion List', "
        "exclusion_effective_date='2023-01-01' WHERE npi='1111111114'"
    )
    conn.commit()

    refs = _load_refs(conn)

    print(f"  Step 3/8 — inserting {len(CLAIM_SPECS)} claims")
    claim_data = _insert_claims(conn, refs)

    print(f"  Step 4/8 — inserting {len(CLAIM_SPECS)} cases + likelihood_scores")
    _insert_cases(conn, claim_data, refs)

    print("  Step 5/8 — running detectors (async)")
    conn.close()  # close sync connection before async opens its own
    seqs_to_run = [s["seq"] for s in CLAIM_SPECS]
    detector_results = asyncio.run(_run_detectors_async(seqs_to_run, db_path))

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")

    print("  Step 6/8 — updating overpayment amounts and priority scores")
    _update_case_overpayments(conn, detector_results)
    _update_priority_scores(conn)

    print("  Step 7/8 — creating 835 ERA transactions")
    # Recovery ERA for case 14 first (so _create_all_eras overwrites the link
    # with the original payment ERA, showing the overpayment in the UI)
    _create_era_for_case14(conn, claim_data)
    _create_all_eras(conn, claim_data)  # links ALL claims to payment ERAs

    print("  Step 8/8 — audit trails and workflow records")
    _create_audit_trails(conn, claim_data, refs)
    _create_notice_for_case7(conn, claim_data)

    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()

    _print_summary(conn, detector_results)
    conn.close()


if __name__ == "__main__":
    run()
