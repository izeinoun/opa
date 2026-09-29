"""seed_low_evidence_demo_case.py — one curated HIGH-DOLLAR / LOW-EVIDENCE case.

ADDITIVE and IDEMPOTENT. Owns exactly `OPA-2026-00021`; a re-run deletes only
that case (+ its claim/lines/finding) before re-inserting. Curated OPA-2026 and
synthetic OPA-CAP cases are never touched.

WHY THIS EXISTS
---------------
Every other seeded case carries 3+ findings, so the Noisy-OR evidence combiner
(`E = 1 - Π(1 - fᵢ)`) drives their evidence score to ~0.98-1.00. When evidence is
~1 for everyone, priority = evidence × amount collapses to *just amount* and the
worklist orders identically to the dollar column — so the demo claim "priority is
expected value, not sticker price" has nothing to point at.

This case breaks that: it is the **second-largest by dollars ($6,480)** but has a
**single weak finding (confidence 0.18)**, so its evidence score is ~0.20 and its
live priority lands ~28 — BELOW cases a quarter its size (00013 @ $1,770 → ~37,
00009 @ $1,386 → ~31). That is the honest "big sticker price, low confidence it'll
stick, so it isn't worth the auditor's morning yet" story.

Design notes that keep it robust:
  - Service lines are paid AT the fee-schedule allowed amount (no paid>allowed
    overage), so a deterministic detector (e.g. DET-04) will NOT fire and inflate
    evidence if someone clicks "Re-run" on the case.
  - The lone finding is a soft medical-necessity call (DET-18), which is inherently
    low-confidence — coherent with a 0.18 score.
  - The divergence is visible on the WORKLIST itself (Amount vs Priority vs EV
    columns); you don't need to open the case to make the point.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")

CASE_NUMBER = "OPA-2026-00021"
CASE_SEQ = 21
ICN = "CLM-2026-00021"

# Cardiology provider (high RF score) + a low-risk cardiac presentation → the
# necessity of repeat catheterizations is genuinely arguable.
PROVIDER_NPI = "1111111111"                               # Dr. Elena Vasquez
PROVIDER_ORG = "c2e5645b-9a3c-4d6e-9736-be2ee72865ff"
PROVIDER_SCORE = 0.9437
MEMBER_ID = "2787c803-b4ad-46f6-840f-b287ebc84332"        # Walter Pryor, MA
LOB = "MA"
CPT = "93458"                                             # diagnostic cardiac cath
PRIMARY_ICD = "R07.9"                                     # chest pain, unspecified
DETECTOR = "DET-18"                                       # medical necessity (soft)

AMOUNT_AT_RISK = 6480.00        # 4 caths × 1,620 allowed — second-largest by $
LINE_ALLOWED = 1620.00
N_LINES = 4
CONFIDENCE = 0.18               # deliberately weak → evidence ≈ 0.20

# Real evidence-scoring constants (case_service): E = 1 - (1-L)·Π(1-fᵢ), L=0.03.
_RULE_LEAK = 0.03
# Real priority formula (scoring_service, Option B / EMV):
#   score = (min(EMV/amount_cap,1)·severity_w + urgency·urgency_w) · 100
_AMOUNT_CAP = 5000.0
_SEVERITY_W = 0.95
_URGENCY_W = 0.05
# Deadline is ~50 days out — OUTSIDE the 30-day urgency window — so the live
# scorer uses urgency_factor 0.0 (not the no-deadline 0.5 default). Match it so
# the stored priority_score and the priority_breakdown panel agree exactly.
_URGENCY = 0.0


def _clear_prior(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT case_id, claim_id FROM opa_cases WHERE case_number = ?",
        (CASE_NUMBER,),
    ).fetchone()
    if not row:
        return
    case_id, claim_id = row
    conn.execute("DELETE FROM case_findings WHERE case_id = ?", (case_id,))
    conn.execute("DELETE FROM likelihood_scores WHERE case_id = ?", (case_id,))
    conn.execute("DELETE FROM opa_cases WHERE case_id = ?", (case_id,))
    if claim_id:
        conn.execute("DELETE FROM findings WHERE claim_id = ?", (claim_id,))
        conn.execute("DELETE FROM claim_lines WHERE claim_id = ?", (claim_id,))
        conn.execute("DELETE FROM claims WHERE claim_id = ?", (claim_id,))
    conn.commit()
    print(f"    Cleared prior {CASE_NUMBER}")


def run(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        # Guard: refs must exist (skip cleanly on a bare DB).
        if not conn.execute(
            "SELECT 1 FROM providers WHERE npi = ?", (PROVIDER_NPI,)
        ).fetchone() or not conn.execute(
            "SELECT 1 FROM members WHERE member_id = ?", (MEMBER_ID,)
        ).fetchone():
            print("    Skipping low-evidence demo case: provider/member not seeded yet")
            return

        _clear_prior(conn)

        NOW = datetime.now().isoformat()
        case_id, claim_id = str(uuid4()), str(uuid4())
        identified = date.today() - timedelta(days=10)
        deadline = identified + timedelta(days=60)          # ~+50d → urgency 0.5
        svc = (identified - timedelta(days=30)).isoformat()
        total_paid = round(LINE_ALLOWED * N_LINES, 2)
        billed = round(total_paid * 1.15, 2)

        # --- derived, honest metrics (for the stored columns; the API recomputes
        #     evidence/EV/priority live, and this matches that computation) ---
        evidence = 1 - (1 - _RULE_LEAK) * (1 - CONFIDENCE)
        emv = evidence * AMOUNT_AT_RISK
        priority_score = round(
            (min(emv / _AMOUNT_CAP, 1.0) * _SEVERITY_W + _URGENCY * _URGENCY_W) * 100, 2
        )
        priority = "HIGH" if priority_score >= 75 else "MEDIUM" if priority_score >= 50 else "LOW"
        print(f"    {CASE_NUMBER}: amount=${AMOUNT_AT_RISK:,.0f}  conf={CONFIDENCE}  "
              f"→ evidence≈{evidence:.3f}  EV≈${emv:,.0f}  priority≈{priority_score} ({priority})")

        conn.execute(
            "INSERT INTO claims (claim_id, icn, member_id, provider_org_id, "
            "billing_provider_npi, rendering_provider_npi, lob, service_from_date, "
            "service_to_date, claim_type, claim_status, total_billed, total_paid, "
            "paid_date, submission_date, pos_code, primary_icd, raw_claim_json, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (claim_id, ICN, MEMBER_ID, PROVIDER_ORG, PROVIDER_NPI, PROVIDER_NPI, LOB,
             svc, svc, "professional", "paid", billed, total_paid,
             (date.fromisoformat(svc) + timedelta(days=20)).isoformat(),
             (date.fromisoformat(svc) + timedelta(days=14)).isoformat(),
             "11", PRIMARY_ICD, json.dumps({"icn": ICN, "profile": "low_evidence_high_dollar"}),
             NOW, NOW),
        )
        for ln_no in range(1, N_LINES + 1):
            # paid == allowed → no paid>allowed overage → deterministic detectors stay quiet.
            conn.execute(
                "INSERT INTO claim_lines (claim_line_id, claim_id, line_number, cpt_code, "
                "service_date, diag_1, modifier_1, units_billed, units_paid, billed_amount, "
                "paid_amount, allowed_amount, pos_code) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (str(uuid4()), claim_id, ln_no, CPT, svc, PRIMARY_ICD, None,
                 1, 1, round(LINE_ALLOWED * 1.15, 2), LINE_ALLOWED, LINE_ALLOWED, "11"),
            )

        conn.execute(
            "INSERT INTO opa_cases (case_id, case_number, case_sequence, claim_id, "
            "primary_detector_id, lob, provider_org_id, member_id, assigned_analyst_id, "
            "status, pipeline_mode, is_active, priority, priority_score, review_time_minutes, "
            "total_overpayment_amount, recommended_recovery_method, identified_date, "
            "deadline_date, deadline_breached, lookback_window_start, is_sensitive_provider, "
            "requires_supervisor_approval, law_enforcement_hold, siu_frozen, evidence_bundle, "
            "case_json, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (case_id, CASE_NUMBER, CASE_SEQ, claim_id, DETECTOR, LOB, PROVIDER_ORG, MEMBER_ID,
             None, "new", "post_pay", 1, priority, priority_score, 0,
             AMOUNT_AT_RISK, "offset", identified.isoformat(), deadline.isoformat(), 0,
             (date.fromisoformat(svc) - timedelta(days=365)).isoformat(), 0, 0, 0, 0,
             json.dumps({"detector": DETECTOR, "profile": "low_evidence_high_dollar"}),
             json.dumps({"seq": CASE_SEQ}), NOW, NOW),
        )
        conn.execute(
            "INSERT INTO likelihood_scores (score_id, case_id, provider_risk_score, "
            "cpt_risk_score, dx_cpt_mismatch_score, claim_complexity_score, "
            "billing_variance_score, composite_likelihood, urgency_factor, "
            "urgency_override_applied, priority_score, score_json, scored_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(uuid4()), case_id, PROVIDER_SCORE, 0.0, 0.0, 0.0, PROVIDER_SCORE,
             PROVIDER_SCORE, _URGENCY, 0, priority_score, json.dumps({}), NOW),
        )
        finding_id = str(uuid4())
        conn.execute(
            "INSERT INTO findings (finding_id, claim_id, detector_id, detector_version, "
            "fired_at, overpayment_amount, severity, confidence, title, rationale, "
            "evidence, status, fwa_indicator) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (finding_id, claim_id, DETECTOR, "v1", NOW, AMOUNT_AT_RISK, "medium", CONFIDENCE,
             "Possible medical-necessity concern",
             "Four diagnostic cardiac catheterizations (CPT 93458) on a low-risk "
             "chest-pain presentation (R07.9). Medical necessity is weakly supported "
             "and coverage is indeterminate — documentation may substantiate. Flagged "
             "for review, but confidence is low: large dollars, soft evidence.",
             json.dumps({"financial_impact": True}), "open", 0),
        )
        conn.execute("INSERT INTO case_findings (case_id, finding_id) VALUES (?,?)",
                     (case_id, finding_id))

        conn.commit()
        print(f"    Inserted {CASE_NUMBER} (high-dollar / low-evidence demo case)")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
