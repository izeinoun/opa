"""Seed 155 cases (OPA-2024-00001 – OPA-2024-00155) — synchronous sqlite3.

Also creates:
  - Transaction835 + ClaimPayment835 reversal rows for 25 closed_recovered cases
  - CaseGroup rows (25 groups linking related claims)
  - Finding rows (~170 total)
  - CaseFinding join rows
  - LikelihoodScore rows

Likelihood formula:
  composite = cpt_risk×0.30 + provider_risk×0.25 + dx_cpt_mismatch×0.20
              + claim_complexity×0.15 + billing_variance×0.10

Priority formula:
  priority_score = (amount_norm×0.40 + composite×0.40 + urgency×0.20) × 100
  deadline ≤5 days from today → force HIGH priority
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW_DT  = datetime(2024, 6, 1, 8, 0, 0)
NOW     = NOW_DT.isoformat()
TODAY   = NOW_DT.date()

# Detector IDs used in findings
DETECTORS = {
    "excess_units":       "EXCESS_UNITS_V1",
    "upcoding":           "UPCODING_V1",
    "duplicate":          "DUPLICATE_CLAIM_V1",
    "dx_cpt_mismatch":    "DX_CPT_MISMATCH_V1",
    "billing_variance":   "BILLING_VARIANCE_V1",
    "retro_termination":  "RETRO_TERM_V1",
    "post_death_billing": "POST_DEATH_V1",
    "multi_line":         "MULTI_LINE_COMPLEXITY_V1",
    "general":            "GENERAL_REVIEW_V1",
}

# Provider billing_variance_scores (approximate post-ML values)
PROVIDER_BV = {
    "1111111111": 0.72,
    "1111111112": 0.61,
    "1111111113": 0.38,
    "1111111114": 0.81,
    "2222222221": 0.29,
    "2222222222": 0.44,
    "2222222223": 0.18,
    "3333333331": 0.35,
    "3333333332": 0.15,
    "3333333333": 0.46,
}

# CPT risk scores (from seed_codes)
CPT_RISK = {
    "99213": 0.10, "99214": 0.20, "99215": 0.30, "99232": 0.35,
    "93000": 0.15, "93306": 0.40, "93458": 0.70, "27447": 0.65,
    "29881": 0.55, "97110": 0.25, "97530": 0.30, "70553": 0.35,
    "72148": 0.25, "99285": 0.45, "99291": 0.60,
}

# CPT-ICD mismatch scores (from seed_codes — key pairs only)
MISMATCH = {
    ("93458", "M17.11"): 0.92, ("93458", "M54.5"): 0.88,
    ("27447", "I10"):    0.75, ("99215", "Z00.00"): 0.65,
    ("93306", "M17.12"): 0.80, ("97110", "I25.10"): 0.70,
    ("93458", "E11.9"):  0.55, ("27447", "G43.909"): 0.82,
    ("72148", "I25.10"): 0.50, ("70553", "M54.5"):   0.42,
}


def _compute_likelihood(
    cpt_code: str,
    icd_code: str,
    rendering_npi: str,
    line_count: int,
    total_paid: float,
) -> dict:
    cpt_risk      = CPT_RISK.get(cpt_code, 0.20)
    provider_risk = PROVIDER_BV.get(rendering_npi, 0.30)
    dx_mismatch   = MISMATCH.get((cpt_code, icd_code), 0.15)
    complexity    = min(1.0, line_count / 4.0)
    bv_score      = PROVIDER_BV.get(rendering_npi, 0.30)

    composite = (
        cpt_risk    * 0.30
        + provider_risk * 0.25
        + dx_mismatch   * 0.20
        + complexity    * 0.15
        + bv_score      * 0.10
    )

    amount_norm = min(1.0, total_paid / 2000.0)
    urgency     = 0.60  # default urgency factor
    priority_score = (amount_norm * 0.40 + composite * 0.40 + urgency * 0.20) * 100

    return {
        "cpt_risk_score":          round(cpt_risk, 4),
        "provider_risk_score":     round(provider_risk, 4),
        "dx_cpt_mismatch_score":   round(dx_mismatch, 4),
        "claim_complexity_score":  round(complexity, 4),
        "billing_variance_score":  round(bv_score, 4),
        "composite_likelihood":    round(composite, 4),
        "urgency_factor":          round(urgency, 4),
        "priority_score":          round(priority_score, 2),
    }


def _priority_label(score: float, deadline: date) -> str:
    if (deadline - TODAY).days <= 5:
        return "HIGH"
    if score >= 70:
        return "HIGH"
    if score >= 45:
        return "MEDIUM"
    return "LOW"


def _status_for_seq(seq: int) -> str:
    """Distribute 155 cases across statuses."""
    if seq <= 25:    return "closed_recovered"
    if seq <= 40:    return "closed_unrecoverable"
    if seq <= 55:    return "pending_dispute"
    if seq <= 75:    return "in_review"
    if seq <= 100:   return "pending_provider_response"
    return "identified"


def _recovery_method(lob: str, amount: float) -> str:
    if amount >= 500:
        return "offset"
    if lob == "Medicaid":
        return "invoice"
    return "offset"


def run(db_path: str = DB_PATH) -> list[dict]:
    conn = sqlite3.connect(db_path)
    try:
        if conn.execute("SELECT COUNT(*) FROM opa_cases").fetchone()[0]:
            print("  opa_cases already seeded — skipping")
            return []

        # ── Load reference data ───────────────────────────────────────────
        claims = conn.execute(
            "SELECT claim_id, icn, member_id, provider_org_id, "
            "billing_provider_npi, rendering_provider_npi, lob, "
            "service_from_date, primary_icd, claim_status, total_paid "
            "FROM claims ORDER BY icn"
        ).fetchall()
        claim_cols = ["claim_id","icn","member_id","provider_org_id",
                      "billing_provider_npi","rendering_provider_npi","lob",
                      "service_from_date","primary_icd","claim_status","total_paid"]
        claims = [dict(zip(claim_cols, row)) for row in claims]

        claim_lines = {}
        for row in conn.execute(
            "SELECT claim_id, line_number, cpt_code, units_billed FROM claim_lines"
        ).fetchall():
            claim_lines.setdefault(row[0], []).append({"line_number": row[1],
                                                        "cpt_code": row[2],
                                                        "units_billed": row[3]})

        analysts = conn.execute(
            "SELECT user_id FROM opa_users WHERE role='analyst' ORDER BY username"
        ).fetchall()
        analyst_ids = [r[0] for r in analysts]

        org_sensitive = {
            row[0]: bool(row[1])
            for row in conn.execute("SELECT provider_org_id, is_sensitive FROM provider_orgs").fetchall()
        }

        # ── Create 25 case groups ─────────────────────────────────────────
        groups: list[dict] = []
        group_id_map: dict[str, str] = {}  # claim_id → group_id
        # Group first 25 claims (duplicate cluster)
        dup_claim_ids = [c["claim_id"] for c in claims[45:70]]  # claims 46-70
        if dup_claim_ids:
            for g_idx in range(min(25, len(dup_claim_ids) // 2 + 1)):
                gid = str(uuid4())
                group_number = f"GRP-2024-{g_idx + 1:05d}"
                ref_claim = claims[45 + g_idx] if 45 + g_idx < len(claims) else claims[0]
                g = {
                    "case_group_id":    gid,
                    "group_number":     group_number,
                    "provider_org_id":  ref_claim["provider_org_id"],
                    "member_id":        ref_claim["member_id"],
                    "dos_range_start":  ref_claim["service_from_date"],
                    "dos_range_end":    ref_claim["service_from_date"],
                    "group_reason":     "Suspected duplicate billing — same member/CPT/DOS pattern",
                    "duplicate_suspected": 1,
                    "created_at":       NOW,
                    "updated_at":       NOW,
                }
                groups.append(g)
                # Assign two claims to this group
                for offset in [0, 1]:
                    idx = 45 + g_idx * 2 + offset
                    if idx < len(claims):
                        group_id_map[claims[idx]["claim_id"]] = gid

        for g in groups:
            conn.execute(
                "INSERT INTO case_groups "
                "(case_group_id, group_number, provider_org_id, member_id, "
                "dos_range_start, dos_range_end, group_reason, "
                "duplicate_suspected, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (g["case_group_id"], g["group_number"], g["provider_org_id"], g["member_id"],
                 g["dos_range_start"], g["dos_range_end"], g["group_reason"],
                 g["duplicate_suspected"], g["created_at"], g["updated_at"]),
            )

        # ── Create 835 transactions for closed_recovered cases ────────────
        # 25 reversal transactions, one per closed_recovered case
        txn_ids: dict[int, str] = {}  # case seq → txn_id
        payment_ids: dict[int, str] = {}
        for i in range(25):
            txn_id = str(uuid4())
            pay_id = str(uuid4())
            txn_ids[i + 1] = txn_id
            payment_ids[i + 1] = pay_id
            ref_claim = claims[i] if i < len(claims) else claims[0]
            conn.execute(
                "INSERT INTO transactions_835 "
                "(transaction_id, transaction_number, transaction_type, payer_name, "
                "provider_org_id, transaction_date, total_amount, claim_count, "
                "raw_835_json, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (txn_id, f"TXN-REV-2024-{i + 1:04d}", "reversal",
                 "CMS Medicare Advantage",
                 ref_claim["provider_org_id"],
                 TODAY.isoformat(),
                 -(ref_claim["total_paid"]), 1,
                 json.dumps({"reversal": True, "icn": ref_claim["icn"]}),
                 NOW),
            )
            # Get first CPT code for this claim
            cpt_row = conn.execute(
                "SELECT cpt_code FROM claim_lines WHERE claim_id=? ORDER BY line_number LIMIT 1",
                (ref_claim["claim_id"],),
            ).fetchone()
            cpt_for_pay = cpt_row[0] if cpt_row else "99213"
            conn.execute(
                "INSERT INTO claim_payments_835 "
                "(payment_id, transaction_id, claim_icn, cpt_code, "
                "paid_amount, adjustment_amount, check_number, payment_date) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (pay_id, txn_id, ref_claim["icn"], cpt_for_pay,
                 -(ref_claim["total_paid"]),
                 ref_claim["total_paid"],
                 f"CHK-REV-{i + 1:04d}",
                 TODAY.isoformat()),
            )
            conn.execute(
                "INSERT INTO era_adjustment_codes "
                "(adjustment_id, payment_id, group_code, reason_code, amount, sequence) "
                "VALUES (?,?,?,?,?,1)",
                (str(uuid4()), pay_id, "PR", "45", ref_claim["total_paid"]),
            )

        # ── Create cases ──────────────────────────────────────────────────
        case_records: list[dict] = []
        for seq, claim in enumerate(claims[:155], 1):
            case_id     = str(uuid4())
            case_number = f"OPA-2024-{seq:05d}"
            status      = _status_for_seq(seq)
            lob         = claim["lob"]
            lines_for_claim = claim_lines.get(claim["claim_id"], [])
            line_count  = len(lines_for_claim)
            cpt_code    = lines_for_claim[0]["cpt_code"] if lines_for_claim else "99213"
            icd_code    = claim["primary_icd"]
            total_paid  = claim["total_paid"]

            identified_date = (TODAY - timedelta(days=60 - seq % 60)).isoformat()
            deadline_date   = (TODAY + timedelta(days=30 - seq % 20)).isoformat()

            scores = _compute_likelihood(
                cpt_code, icd_code, claim["rendering_provider_npi"], line_count, total_paid
            )
            priority = _priority_label(scores["priority_score"], date.fromisoformat(deadline_date))

            # Detector assignment by cluster
            if seq <= 25:
                detector = DETECTORS["excess_units"]
            elif seq <= 45:
                detector = DETECTORS["upcoding"]
            elif seq <= 60:
                detector = DETECTORS["duplicate"]
            elif seq <= 80:
                detector = DETECTORS["dx_cpt_mismatch"]
            elif seq <= 100:
                detector = DETECTORS["billing_variance"]
            elif seq <= 110:
                detector = DETECTORS["retro_termination"]
            elif seq <= 115:
                detector = DETECTORS["post_death_billing"]
            elif seq <= 130:
                detector = DETECTORS["multi_line"]
            else:
                detector = DETECTORS["general"]

            assigned_analyst = analyst_ids[(seq - 1) % len(analyst_ids)] if analyst_ids else None
            sensitive = org_sensitive.get(claim["provider_org_id"], False)
            case_group_id = group_id_map.get(claim["claim_id"])
            requires_sup = bool(sensitive or scores["composite_likelihood"] > 0.70)

            era_txn_id = txn_ids.get(seq) if status == "closed_recovered" else None

            evidence = {
                "detector_id":    detector,
                "claim_icn":      claim["icn"],
                "cpt_code":       cpt_code,
                "icd_code":       icd_code,
                "total_paid":     total_paid,
                "line_count":     line_count,
                "likelihood":     scores["composite_likelihood"],
            }
            case_json = {
                "case_number": case_number,
                "status":      status,
                "scores":      scores,
            }

            recovery_method = _recovery_method(lob, total_paid)
            lookback_start  = (date.fromisoformat(claim["service_from_date"]) - timedelta(days=365)).isoformat()

            c = {
                "case_id":                    case_id,
                "case_number":                case_number,
                "case_sequence":              seq,
                "claim_id":                   claim["claim_id"],
                "case_group_id":              case_group_id,
                "primary_detector_id":        detector,
                "lob":                        lob,
                "provider_org_id":            claim["provider_org_id"],
                "member_id":                  claim["member_id"],
                "assigned_analyst_id":        assigned_analyst,
                "status":                     status,
                "is_active":                  1 if status not in ("closed_recovered","closed_unrecoverable") else 0,
                "priority":                   priority,
                "priority_score":             scores["priority_score"],
                "total_overpayment_amount":   round(total_paid * 0.85, 2),
                "recommended_recovery_method":recovery_method,
                "identified_date":            identified_date,
                "deadline_date":              deadline_date,
                "deadline_breached":          0,
                "lookback_window_start":      lookback_start,
                "provider_response_due_date": (date.fromisoformat(identified_date) + timedelta(days=30)).isoformat(),
                "is_sensitive_provider":      int(sensitive),
                "requires_supervisor_approval":int(requires_sup),
                "evidence_bundle":            json.dumps(evidence),
                "case_json":                  json.dumps(case_json),
                "created_at":                 NOW,
                "updated_at":                 NOW,
            }
            case_records.append(c)

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
                    c["case_id"], c["case_number"], c["case_sequence"], c["claim_id"],
                    c["case_group_id"], c["primary_detector_id"], c["lob"],
                    c["provider_org_id"], c["member_id"], c["assigned_analyst_id"],
                    c["status"], c["is_active"], c["priority"], c["priority_score"],
                    c["total_overpayment_amount"], c["recommended_recovery_method"],
                    c["identified_date"], c["deadline_date"], c["deadline_breached"],
                    c["lookback_window_start"], c["provider_response_due_date"],
                    c["is_sensitive_provider"], c["requires_supervisor_approval"],
                    c["evidence_bundle"], c["case_json"], c["created_at"], c["updated_at"],
                ),
            )

            # Update claim.era_transaction_id for closed_recovered
            if era_txn_id:
                conn.execute(
                    "UPDATE claims SET era_transaction_id=? WHERE claim_id=?",
                    (era_txn_id, claim["claim_id"]),
                )

            # ── Finding ──────────────────────────────────────────────────
            finding_id = str(uuid4())
            fired_at   = (datetime.fromisoformat(identified_date) + timedelta(hours=1)).isoformat()
            rationale  = (
                f"Detector {detector} fired on claim {claim['icn']}: "
                f"CPT {cpt_code} with ICD {icd_code}, paid ${total_paid:.2f}. "
                f"Composite likelihood: {scores['composite_likelihood']:.3f}."
            )
            conn.execute(
                "INSERT INTO findings "
                "(finding_id, claim_id, claim_line_id, detector_id, detector_version, "
                "fired_at, overpayment_amount, severity, confidence, "
                "rationale, evidence, rule_version, status) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    finding_id, claim["claim_id"], None,
                    detector, "1.0.0", fired_at,
                    c["total_overpayment_amount"],
                    "HIGH" if scores["composite_likelihood"] > 0.55 else "MEDIUM",
                    scores["composite_likelihood"],
                    rationale,
                    json.dumps(evidence),
                    "1.0.0",
                    "confirmed" if status in ("closed_recovered","closed_unrecoverable") else "open",
                ),
            )

            # case_findings join
            conn.execute(
                "INSERT INTO case_findings (case_id, finding_id) VALUES (?,?)",
                (case_id, finding_id),
            )

            # ── LikelihoodScore ──────────────────────────────────────────
            conn.execute(
                "INSERT INTO likelihood_scores "
                "(score_id, case_id, provider_risk_score, cpt_risk_score, "
                "dx_cpt_mismatch_score, claim_complexity_score, billing_variance_score, "
                "composite_likelihood, urgency_factor, urgency_override_applied, "
                "priority_score, score_json, scored_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()), case_id,
                    scores["provider_risk_score"],
                    scores["cpt_risk_score"],
                    scores["dx_cpt_mismatch_score"],
                    scores["claim_complexity_score"],
                    scores["billing_variance_score"],
                    scores["composite_likelihood"],
                    scores["urgency_factor"],
                    0,
                    scores["priority_score"],
                    json.dumps(scores),
                    NOW,
                ),
            )

        conn.commit()
        print(f"  Inserted {len(case_records)} cases, {len(groups)} groups, "
              f"25 ERA reversal txns, {len(case_records)} findings")
        return case_records
    finally:
        conn.close()


if __name__ == "__main__":
    run()
