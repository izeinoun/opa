"""Seed 155 claims (CLM-2024-00001 – CLM-2024-00155) — synchronous sqlite3.

Each claim has 1-4 claim lines. Line-count distribution:
  78 single-line, 46 two-line, 24 three-line, 7 four-line

Detector targeting (approximate row counts):
  excess_units          : 25 claims  — units_billed > typical_units_max
  upcoding              : 20 claims  — CPT escalation patterns
  duplicate             : 15 claims  — same member/CPT/DOS, different ICN
  dx_cpt_mismatch       : 20 claims  — high mismatch-risk CPT/ICD pairs
  billing_variance      : 20 claims  — high-anomaly providers (1111111111/1114)
  retro_termination     : 10 claims  — members with retro_termination_date
  post_death_billing    : 5 claims   — services after date_of_death
  excluded_provider     : (handled at case level; no claims for excluded npis)
  multi_line_complexity : 15 claims  — 3-4 line claims with modifier combos
  general               : 25 claims  — mixed / baseline
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW = "2024-01-01T08:00:00.000000"

# ── helpers ────────────────────────────────────────────────────────────────

def _d(s: str) -> str:
    return s  # dates already ISO strings


def _icn(n: int) -> str:
    return f"CLM-2024-{n:05d}"


# ── reference lookups ─────────────────────────────────────────────────────

def _load_refs(conn: sqlite3.Connection) -> dict:
    members = {
        row[0]: {"member_id": row[1], "lob": row[2],
                 "cov_term": row[3], "retro_term": row[4], "dod": row[5]}
        for row in conn.execute(
            "SELECT member_number, member_id, lob, coverage_termination_date, "
            "retro_termination_date, date_of_death FROM members"
        ).fetchall()
    }
    providers = {
        row[0]: {"provider_id": row[1], "org_id": row[2]}
        for row in conn.execute(
            "SELECT npi, provider_id, provider_org_id FROM providers"
        ).fetchall()
    }
    orgs = {
        row[0]: row[1]
        for row in conn.execute("SELECT npi, provider_org_id FROM provider_orgs").fetchall()
    }
    return {"members": members, "providers": providers, "orgs": orgs}


# ── claim factory ─────────────────────────────────────────────────────────

def _make_claim(
    seq: int,
    member_number: str,
    billing_npi: str,
    rendering_npi: str,
    org_npi: str,
    lob: str,
    service_from: str,
    service_to: str,
    primary_icd: str,
    claim_type: str,
    lines: list[dict],
    *,
    auth_number: str | None = None,
    pos_code: str = "11",
    submission_offset_days: int = 14,
    refs: dict,
) -> tuple[dict, list[dict]]:
    """Return (claim_dict, line_dicts) without inserting."""
    claim_id = str(uuid4())
    member_id = refs["members"][member_number]["member_id"]
    org_id    = refs["orgs"][org_npi]

    total_billed = round(sum(ln["billed_amount"] for ln in lines), 2)
    total_paid   = round(sum(ln["paid_amount"]   for ln in lines), 2)

    svc_date = date.fromisoformat(service_from)
    paid_date = (svc_date + timedelta(days=20)).isoformat()
    submit_date = (svc_date + timedelta(days=submission_offset_days)).isoformat()

    raw = {
        "icn": _icn(seq),
        "member_number": member_number,
        "billing_npi": billing_npi,
        "rendering_npi": rendering_npi,
        "lines": lines,
    }

    claim = {
        "claim_id":              claim_id,
        "icn":                   _icn(seq),
        "case_group_id":         None,
        "member_id":             member_id,
        "provider_org_id":       org_id,
        "billing_provider_npi":  billing_npi,
        "rendering_provider_npi":rendering_npi,
        "lob":                   lob,
        "service_from_date":     service_from,
        "service_to_date":       service_to,
        "claim_type":            claim_type,
        "claim_status":          "paid",
        "total_billed":          total_billed,
        "total_paid":            total_paid,
        "paid_date":             paid_date,
        "authorization_number":  auth_number,
        "submission_date":       submit_date,
        "pos_code":              pos_code,
        "primary_icd":           primary_icd,
        "era_transaction_id":    None,  # filled later by seed_cases
        "raw_claim_json":        json.dumps(raw),
        "created_at":            NOW,
        "updated_at":            NOW,
    }

    claim_lines = []
    for i, ln in enumerate(lines, 1):
        _codes = ln.get("icd_codes", [primary_icd])
        claim_lines.append({
            "claim_line_id":  str(uuid4()),
            "claim_id":       claim_id,
            "line_number":    i,
            "cpt_code":       ln["cpt_code"],
            "diag_1":         _codes[0] if len(_codes) > 0 else None,
            "diag_2":         _codes[1] if len(_codes) > 1 else None,
            "diag_3":         _codes[2] if len(_codes) > 2 else None,
            "diag_4":         _codes[3] if len(_codes) > 3 else None,
            "modifier_1":     ln.get("modifier_1"),
            "modifier_2":     ln.get("modifier_2"),
            "units_billed":   ln.get("units_billed", 1),
            "units_paid":     ln.get("units_paid", ln.get("units_billed", 1)),
            "billed_amount":  ln["billed_amount"],
            "paid_amount":    ln["paid_amount"],
            "allowed_amount": ln.get("allowed_amount", ln["paid_amount"]),
            "pos_code":       ln.get("pos_code", pos_code),
            "revenue_code":   ln.get("revenue_code"),
        })

    return claim, claim_lines


# ── claim definitions ─────────────────────────────────────────────────────

def _build_claims(refs: dict) -> tuple[list[dict], list[dict]]:
    """Return (all_claims, all_lines)."""
    claims: list[dict]     = []
    lines:  list[dict]     = []
    seq = 1

    def add(c, ls):
        nonlocal seq
        claims.append(c)
        lines.extend(ls)
        seq += 1

    # ── 25 excess_units claims ────────────────────────────────────────────
    for i in range(25):
        member = f"MA-{(i % 10) + 1:06d}" if (i % 10) + 1 <= 16 else f"PPO-{(i % 10) + 1:06d}"
        member = "MA-000001" if i < 10 else "PPO-000001"
        m_info = refs["members"].get(member, refs["members"]["MA-000001"])
        lob    = m_info["lob"]
        npi    = "1111111114"  # internal_high — excess unit pattern
        org    = "9900000001"
        dos    = f"2024-{(i % 11) + 1:02d}-{(i % 28) + 1:02d}"
        c, ls = _make_claim(
            seq, member, npi, npi, org, lob, dos, dos, "E11.9",
            "professional",
            [{"cpt_code": "97110", "units_billed": 8, "units_paid": 4,
              "billed_amount": 336.00, "paid_amount": 168.00, "allowed_amount": 168.00,
              "icd_codes": ["E11.9"]}],
            refs=refs,
        )
        add(c, ls)

    # ── 20 upcoding claims ────────────────────────────────────────────────
    for i in range(20):
        member = "PPO-000003" if i % 2 == 0 else "PPO-000005"
        m_info = refs["members"][member]
        lob    = m_info["lob"]
        npi    = "1111111111"  # cardiology_high
        org    = "9900000001"
        dos    = f"2024-{(i % 12) + 1:02d}-15"
        c, ls = _make_claim(
            seq, member, npi, npi, org, lob, dos, dos, "I25.10",
            "professional",
            [{"cpt_code": "99215", "units_billed": 1, "units_paid": 1,
              "billed_amount": 155.00, "paid_amount": 155.00, "allowed_amount": 130.00,
              "icd_codes": ["I25.10"]}],
            refs=refs,
        )
        add(c, ls)

    # ── 15 duplicate claims ───────────────────────────────────────────────
    # Pairs: claims seq 46-60 duplicate DOS/CPT of claims 46-52 (7 originals + 8 dups)
    dup_base_seq = seq
    for i in range(15):
        member = "MA-000002" if i % 2 == 0 else "MA-000004"
        m_info = refs["members"][member]
        lob    = m_info["lob"]
        npi    = "2222222222"  # emergency_std
        org    = "9900000002"
        dos    = f"2024-0{(i % 9) + 1}-{(i % 28) + 1:02d}"
        c, ls = _make_claim(
            seq, member, npi, npi, org, lob, dos, dos, "R07.9",
            "professional",
            [{"cpt_code": "99285", "units_billed": 1, "units_paid": 1,
              "billed_amount": 225.00, "paid_amount": 225.00, "allowed_amount": 225.00,
              "icd_codes": ["R07.9"]}],
            refs=refs,
        )
        add(c, ls)

    # ── 20 dx_cpt_mismatch claims ─────────────────────────────────────────
    mismatch_pairs = [
        ("93458", "M17.11", 1320.00),
        ("93458", "M54.5",  1320.00),
        ("27447", "I10",    1500.00),
        ("99215", "Z00.00", 155.00),
        ("93306", "M17.12", 456.00),
        ("97110", "I25.10", 42.00),
        ("93458", "E11.9",  1320.00),
        ("27447", "G43.909",1500.00),
        ("72148", "I25.10", 380.00),
        ("70553", "M54.5",  520.00),
    ]
    for i in range(20):
        pair  = mismatch_pairs[i % len(mismatch_pairs)]
        cpt, icd, amt = pair
        member = "PPO-000007" if i % 3 == 0 else ("MA-000006" if i % 3 == 1 else "PPO-000009")
        m_info = refs["members"][member]
        lob    = m_info["lob"]
        npi    = "1111111112"  # ortho_high
        org    = "9900000001"
        dos    = f"2024-{(i % 12) + 1:02d}-{(i % 25) + 3:02d}"
        c, ls = _make_claim(
            seq, member, npi, npi, org, lob, dos, dos, icd,
            "professional",
            [{"cpt_code": cpt, "units_billed": 1, "units_paid": 1,
              "billed_amount": amt, "paid_amount": amt * 0.85, "allowed_amount": amt * 0.85,
              "icd_codes": [icd]}],
            refs=refs,
        )
        add(c, ls)

    # ── 20 billing_variance claims ────────────────────────────────────────
    for i in range(20):
        member = "MA-000009" if i % 2 == 0 else "MA-000010"
        m_info = refs["members"][member]
        lob    = m_info["lob"]
        npi    = "1111111111"  # cardiology_high
        org    = "9900000001"
        dos    = f"2024-{(i % 12) + 1:02d}-10"
        c, ls = _make_claim(
            seq, member, npi, npi, org, lob, dos, dos, "I25.10",
            "professional",
            [{"cpt_code": "93458", "units_billed": 1, "units_paid": 1,
              "billed_amount": 1320.00, "paid_amount": 1188.00, "allowed_amount": 1188.00,
              "icd_codes": ["I25.10"]}],
            auth_number=f"AUTH-{i+1000:04d}",
            refs=refs,
        )
        add(c, ls)

    # ── 10 retro_termination claims ───────────────────────────────────────
    retro_members = ["MA-000011", "MA-000012", "MA-000013"]
    for i in range(10):
        member = retro_members[i % len(retro_members)]
        m_info = refs["members"][member]
        lob    = m_info["lob"]
        # Service after retro_termination_date
        dos    = "2023-11-15" if member == "MA-000011" else (
                 "2023-05-10" if member == "MA-000012" else "2023-11-20")
        npi    = "2222222223"  # internal_low (clean provider, date issue only)
        org    = "9900000002"
        c, ls = _make_claim(
            seq, member, npi, npi, org, lob, dos, dos, "I10",
            "professional",
            [{"cpt_code": "99214", "units_billed": 1, "units_paid": 1,
              "billed_amount": 115.00, "paid_amount": 115.00, "allowed_amount": 115.00,
              "icd_codes": ["I10"]}],
            refs=refs,
        )
        add(c, ls)

    # ── 5 post_death_billing claims ───────────────────────────────────────
    dead_members = ["MA-000014", "MA-000015"]
    for i in range(5):
        member = dead_members[i % len(dead_members)]
        m_info = refs["members"][member]
        lob    = m_info["lob"]
        dod    = m_info["dod"]
        # Service after date_of_death
        after_death = (date.fromisoformat(dod) + timedelta(days=5)).isoformat()
        npi    = "2222222221"  # cardiology_std
        org    = "9900000002"
        c, ls = _make_claim(
            seq, member, npi, npi, org, lob, after_death, after_death, "I25.10",
            "professional",
            [{"cpt_code": "93000", "units_billed": 1, "units_paid": 1,
              "billed_amount": 19.00, "paid_amount": 19.00, "allowed_amount": 19.00,
              "icd_codes": ["I25.10"]}],
            refs=refs,
        )
        add(c, ls)

    # ── 15 multi_line_complexity claims ──────────────────────────────────
    multi_configs = [
        # 3-line
        [
            {"cpt_code": "99232", "units_billed": 1, "units_paid": 1,
             "billed_amount": 112.00, "paid_amount": 112.00, "allowed_amount": 112.00,
             "modifier_1": "25", "icd_codes": ["I25.10"]},
            {"cpt_code": "93000", "units_billed": 1, "units_paid": 1,
             "billed_amount": 19.00, "paid_amount": 19.00, "allowed_amount": 19.00,
             "icd_codes": ["I25.10"]},
            {"cpt_code": "93306", "units_billed": 1, "units_paid": 1,
             "billed_amount": 456.00, "paid_amount": 410.40, "allowed_amount": 410.40,
             "modifier_1": "59", "icd_codes": ["I25.10"]},
        ],
        # 4-line (7 of the 15)
        [
            {"cpt_code": "27447", "units_billed": 1, "units_paid": 1,
             "billed_amount": 1500.00, "paid_amount": 1500.00, "allowed_amount": 1500.00,
             "modifier_1": "RT", "icd_codes": ["M17.11"]},
            {"cpt_code": "27447", "units_billed": 1, "units_paid": 1,
             "billed_amount": 1500.00, "paid_amount": 1500.00, "allowed_amount": 1500.00,
             "modifier_1": "LT", "icd_codes": ["M17.12"]},
            {"cpt_code": "99232", "units_billed": 1, "units_paid": 1,
             "billed_amount": 112.00, "paid_amount": 112.00, "allowed_amount": 112.00,
             "icd_codes": ["M17.11"]},
            {"cpt_code": "29881", "units_billed": 1, "units_paid": 1,
             "billed_amount": 840.00, "paid_amount": 756.00, "allowed_amount": 756.00,
             "modifier_1": "59", "icd_codes": ["M17.11"]},
        ],
    ]
    for i in range(15):
        member = "PPO-000011" if i % 2 == 0 else "PPO-000013"
        m_info = refs["members"][member]
        lob    = m_info["lob"]
        ln_cfg = multi_configs[0] if i < 8 else multi_configs[1]
        npi    = "3333333331"  # ortho_std
        org    = "9900000003"
        dos    = f"2024-{(i % 12) + 1:02d}-20"
        c, ls = _make_claim(
            seq, member, npi, npi, org, lob, dos, dos, "M17.11",
            "professional",
            ln_cfg,
            refs=refs,
        )
        add(c, ls)

    # ── 25 general / baseline claims ──────────────────────────────────────
    general_cfg = [
        ("PPO-000002",  "2222222221", "9900000002", "I10",    "99213", 77.00,   "PPO"),
        ("PPO-000004",  "2222222221", "9900000002", "E11.9",  "99214", 115.00,  "PPO"),
        ("MA-000001",   "3333333332", "9900000003", "M54.5",  "72148", 380.00,  "MA"),
        ("MA-000003",   "3333333332", "9900000003", "G35",    "70553", 520.00,  "MA"),
        ("MCD-000001",  "3333333333", "9900000003", "M54.5",  "97530", 48.00,   "Medicaid"),
        ("MCD-000002",  "3333333333", "9900000003", "E11.9",  "97110", 42.00,   "Medicaid"),
        ("PPO-000006",  "2222222222", "9900000002", "R07.9",  "99285", 225.00,  "PPO"),
        ("PPO-000008",  "2222222222", "9900000002", "J18.9",  "99291", 610.00,  "PPO"),
        ("MA-000005",   "1111111113", "9900000001", "G43.909","99213", 77.00,   "MA"),
        ("MA-000007",   "1111111113", "9900000001", "N18.3",  "99215", 155.00,  "MA"),
        ("PPO-000010",  "2222222223", "9900000002", "I10",    "99213", 77.00,   "PPO"),
        ("PPO-000012",  "2222222223", "9900000002", "E11.9",  "99214", 115.00,  "PPO"),
        ("MA-000008",   "3333333331", "9900000003", "M17.11", "29881", 840.00,  "MA"),
        ("MA-000016",   "3333333331", "9900000003", "S82.001A","27447",1500.00, "MA"),
        ("MCD-000003",  "3333333333", "9900000003", "M54.5",  "97110", 42.00,   "Medicaid"),
        ("MCD-000004",  "2222222223", "9900000002", "E11.9",  "99213", 77.00,   "Medicaid"),
        ("PPO-000014",  "2222222221", "9900000002", "I25.10", "93000", 19.00,   "PPO"),
        ("PPO-000016",  "2222222221", "9900000002", "R07.9",  "93000", 19.00,   "PPO"),
        ("MA-000006",   "1111111114", "9900000001", "E11.9",  "99215", 155.00,  "MA"),
        ("MA-000004",   "1111111114", "9900000001", "I10",    "99214", 115.00,  "MA"),
        ("PPO-000015",  "3333333332", "9900000003", "M54.5",  "72148", 380.00,  "PPO"),
        ("MCD-000005",  "3333333333", "9900000003", "M54.5",  "97530", 48.00,   "Medicaid"),
        ("MCD-000006",  "3333333333", "9900000003", "E11.9",  "97110", 42.00,   "Medicaid"),
        ("MCD-000007",  "2222222223", "9900000002", "I10",    "99213", 77.00,   "Medicaid"),
        ("MCD-000008",  "3333333333", "9900000003", "M54.5",  "97530", 48.00,   "Medicaid"),
    ]
    for i, (member, npi, org_npi, icd, cpt, amt, lob) in enumerate(general_cfg):
        dos = f"2024-{(i % 12) + 1:02d}-{(i % 25) + 1:02d}"
        c, ls = _make_claim(
            seq, member, npi, npi, org_npi, lob, dos, dos, icd,
            "professional",
            [{"cpt_code": cpt, "units_billed": 1, "units_paid": 1,
              "billed_amount": amt, "paid_amount": amt * 0.90, "allowed_amount": amt * 0.90,
              "icd_codes": [icd]}],
            refs=refs,
        )
        add(c, ls)

    return claims, lines


# ── insert ────────────────────────────────────────────────────────────────

def run(db_path: str = DB_PATH) -> tuple[list[dict], list[dict]]:
    conn = sqlite3.connect(db_path)
    try:
        if conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]:
            print("  claims already seeded — skipping")
            # Return existing for downstream use
            c_rows = [dict(zip(
                ["claim_id","icn","member_id","provider_org_id",
                 "billing_provider_npi","rendering_provider_npi","lob",
                 "service_from_date","primary_icd","claim_status","total_paid"],
                row))
                for row in conn.execute(
                    "SELECT claim_id,icn,member_id,provider_org_id,"
                    "billing_provider_npi,rendering_provider_npi,lob,"
                    "service_from_date,primary_icd,claim_status,total_paid "
                    "FROM claims ORDER BY icn"
                ).fetchall()]
            return c_rows, []

        refs = _load_refs(conn)
        all_claims, all_lines = _build_claims(refs)

        for c in all_claims:
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
                    c["claim_id"], c["icn"], c["case_group_id"], c["member_id"],
                    c["provider_org_id"], c["billing_provider_npi"], c["rendering_provider_npi"],
                    c["lob"], c["service_from_date"], c["service_to_date"], c["claim_type"],
                    c["claim_status"], c["total_billed"], c["total_paid"], c["paid_date"],
                    c["authorization_number"], c["submission_date"], c["pos_code"],
                    c["primary_icd"], c["era_transaction_id"], c["raw_claim_json"],
                    c["created_at"], c["updated_at"],
                ),
            )

        for ln in all_lines:
            conn.execute(
                "INSERT INTO claim_lines "
                "(claim_line_id, claim_id, line_number, cpt_code, "
                "diag_1, diag_2, diag_3, diag_4, "
                "modifier_1, modifier_2, units_billed, units_paid, "
                "billed_amount, paid_amount, allowed_amount, pos_code, revenue_code) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ln["claim_line_id"], ln["claim_id"], ln["line_number"], ln["cpt_code"],
                    ln["diag_1"], ln["diag_2"], ln["diag_3"], ln["diag_4"],
                    ln["modifier_1"], ln["modifier_2"],
                    ln["units_billed"], ln["units_paid"],
                    ln["billed_amount"], ln["paid_amount"], ln["allowed_amount"],
                    ln["pos_code"], ln["revenue_code"],
                ),
            )

        conn.commit()
        print(f"  Inserted {len(all_claims)} claims, {len(all_lines)} claim lines")
        return all_claims, all_lines
    finally:
        conn.close()


if __name__ == "__main__":
    run()
