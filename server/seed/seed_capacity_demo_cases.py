"""seed_capacity_demo_cases.py — bulk OPEN cases to demonstrate the EMV capacity cut.

ADDITIVE and IDEMPOTENT. Every case_number is `OPA-CAP-#####`; a re-run deletes
only those before re-inserting, so the curated demo cases are never touched.

Purpose: give the two-stage funnel real volume AND real per-claim signal.
  - Provider spread (P_risk): cases are drawn across the full provider RF-score
    range, so the Stage-1 hand-off feature varies.
  - Claim-feature spread (F4/F5/F7/F8): each case gets one of several service-
    line "profiles" (clean / high-value CPT / multi-line / high-units / modifier-
    heavy) so the Stage 2 Claim Predictor sees varied payment features and emits a
    spread of calibrated per-claim probabilities — not one flat number per provider.
  - Dollar spread (amount_at_risk): wide, so EV = calibrated P × amount has a clear
    top and a visible tail for the capacity cut.

Probability is read live: Stage 2 writes claims.overpayment_probability during the
score-claims pass, and the funnel reads it. Each case also gets one finding +
likelihood_score so it looks complete in the worklist.
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
from datetime import date, datetime, timedelta
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
TODAY = date.today()

CASE_PREFIX = "OPA-CAP-"
ICN_PREFIX = "CLM-CAP-"
SEQ_BASE = 5000
DEFAULT_N = 80

_OPEN_STATUSES = ["new", "assigned", "in_review", "in_review", "pending_supervisor"]
_DETECTORS = ["DET-04", "DET-01", "DET-06", "DET-02", "DET-09"]
_ICD = "M17.11"

# CPT pools — all present in fee_schedules so F5's fee-schedule term resolves.
# HIGH set is a subset of stage2_features.HIGH_RISK_CPTS (drives F4).
_CPT_HIGH = ["27447", "70553", "99214", "99215", "93000"]
_CPT_NORMAL = ["99213", "97110", "97530", "99232", "93306"]
_HIGH_MODIFIERS = ["59", "25", "76"]

# Service-line profiles → (F4, F5, F7, F8) variety. Weighted mix.
_PROFILES = (
    ["clean"] * 26 + ["high_cpt"] * 22 + ["multiline"] * 16
    + ["high_units"] * 10 + ["modifier"] * 12
)


def _load_refs(conn: sqlite3.Connection) -> dict:
    providers = conn.execute(
        "SELECT npi, provider_org_id, billing_variance_score FROM providers "
        "WHERE provider_org_id IS NOT NULL"
    ).fetchall()
    members = conn.execute("SELECT member_id, lob FROM members").fetchall()
    analysts = [
        r[0] for r in conn.execute(
            "SELECT user_id FROM opa_users WHERE role='analyst' ORDER BY username"
        ).fetchall()
    ]
    return {"providers": providers, "members": members, "analysts": analysts}


def _clear_prior(conn: sqlite3.Connection) -> None:
    case_rows = conn.execute(
        "SELECT case_id, claim_id FROM opa_cases WHERE case_number LIKE ?",
        (CASE_PREFIX + "%",),
    ).fetchall()
    if not case_rows:
        return
    case_ids = [r[0] for r in case_rows]
    claim_ids = [r[1] for r in case_rows if r[1]]
    qc = ",".join("?" * len(case_ids))
    conn.execute(f"DELETE FROM case_findings WHERE case_id IN ({qc})", case_ids)
    conn.execute(f"DELETE FROM likelihood_scores WHERE case_id IN ({qc})", case_ids)
    conn.execute(f"DELETE FROM opa_cases WHERE case_id IN ({qc})", case_ids)
    if claim_ids:
        qcl = ",".join("?" * len(claim_ids))
        conn.execute(f"DELETE FROM findings WHERE claim_id IN ({qcl})", claim_ids)
        conn.execute(f"DELETE FROM claim_lines WHERE claim_id IN ({qcl})", claim_ids)
        conn.execute(f"DELETE FROM claims WHERE claim_id IN ({qcl})", claim_ids)
    conn.commit()
    print(f"    Cleared {len(case_ids)} prior {CASE_PREFIX}* cases")


def _amount_for(rng: random.Random) -> float:
    """Wide overpayment-dollar spread for EV ranking. Heavy tail."""
    r = rng.random()
    if r < 0.45:
        return round(rng.uniform(150, 2_000), 2)
    if r < 0.80:
        return round(rng.uniform(2_000, 12_000), 2)
    return round(rng.uniform(12_000, 60_000), 2)


def _build_lines(profile: str, rng: random.Random) -> list[dict]:
    """Return service lines for a profile. allowed_amount seeds F5 (for modifier
    lines it is set above typical fee-schedule base so allowed − fee > 0)."""
    def line(cpt, units, mod=None, allowed=None):
        return {"cpt": cpt, "units": units, "mod": mod,
                "allowed": allowed if allowed is not None else round(rng.uniform(60, 220), 2)}

    if profile == "clean":                       # F4=0, F8=0, F7 low
        return [line(rng.choice(_CPT_NORMAL), 1)]
    if profile == "high_cpt":                    # F4=1
        return [line(rng.choice(_CPT_HIGH), 1)]
    if profile == "multiline":                   # F8=1, F4 partial
        k = rng.randint(3, 4)
        pool = [rng.choice(_CPT_HIGH)] + [rng.choice(_CPT_NORMAL) for _ in range(k - 1)]
        rng.shuffle(pool)
        return [line(c, rng.randint(1, 2)) for c in pool]
    if profile == "high_units":                  # F7 high, F4=1, F8=1
        return [line(rng.choice(_CPT_HIGH), rng.randint(5, 8)) for _ in range(2)]
    if profile == "modifier":                    # F5>0, F4=1, F8=1
        cpt = rng.choice(["99214", "99215"])
        return [line(cpt, 1, mod=rng.choice(_HIGH_MODIFIERS), allowed=round(rng.uniform(300, 520), 2))
                for _ in range(2)]
    return [line(rng.choice(_CPT_NORMAL), 1)]


def run(db_path: str = DB_PATH, n: int = DEFAULT_N) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        refs = _load_refs(conn)
        if not refs["providers"] or not refs["members"] or not refs["analysts"]:
            print("    Skipping: providers/members/analysts not seeded yet")
            return

        _clear_prior(conn)
        rng = random.Random(42)
        NOW = datetime.now().isoformat()

        profiles = [_PROFILES[i % len(_PROFILES)] for i in range(n)]
        rng.shuffle(profiles)

        inserted = 0
        prof_counts: dict[str, int] = {}
        for i, profile in enumerate(profiles):
            prof_counts[profile] = prof_counts.get(profile, 0) + 1
            seq = SEQ_BASE + i
            case_id, claim_id = str(uuid4()), str(uuid4())
            icn, case_number = f"{ICN_PREFIX}{seq:05d}", f"{CASE_PREFIX}{seq:05d}"

            npi, org_id, score = rng.choice(refs["providers"])   # full P_risk spread
            member_id, lob = rng.choice(refs["members"])
            analyst_id = refs["analysts"][i % len(refs["analysts"])]
            detector = rng.choice(_DETECTORS)
            amount = _amount_for(rng)

            status = _OPEN_STATUSES[i % len(_OPEN_STATUSES)]
            identified_date = TODAY - timedelta(days=rng.randint(3, 62))
            deadline_date = identified_date + timedelta(days=60)
            breached = int(deadline_date < TODAY)
            svc = (identified_date - timedelta(days=40)).isoformat()

            lines = _build_lines(profile, rng)
            total_paid = round(sum(ln["allowed"] for ln in lines), 2)
            billed = round(total_paid * 1.2, 2)
            emv = (score or 0.3) * amount
            priority_score = round(min(emv / 50_000.0, 1.0) * 95 + 5, 2)
            priority = "HIGH" if priority_score >= 75 else "MEDIUM" if priority_score >= 50 else "LOW"

            conn.execute(
                "INSERT INTO claims (claim_id, icn, member_id, provider_org_id, "
                "billing_provider_npi, rendering_provider_npi, lob, service_from_date, "
                "service_to_date, claim_type, claim_status, total_billed, total_paid, "
                "paid_date, submission_date, pos_code, primary_icd, raw_claim_json, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (claim_id, icn, member_id, org_id, npi, npi, lob, svc, svc,
                 "professional", "paid", billed, total_paid,
                 (date.fromisoformat(svc) + timedelta(days=20)).isoformat(),
                 (date.fromisoformat(svc) + timedelta(days=14)).isoformat(),
                 "11", _ICD, json.dumps({"icn": icn, "profile": profile}), NOW, NOW),
            )
            for ln_no, ln in enumerate(lines, 1):
                conn.execute(
                    "INSERT INTO claim_lines (claim_line_id, claim_id, line_number, cpt_code, "
                    "service_date, diag_1, modifier_1, units_billed, units_paid, billed_amount, "
                    "paid_amount, allowed_amount, pos_code) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (str(uuid4()), claim_id, ln_no, ln["cpt"], svc, _ICD, ln["mod"],
                     ln["units"], ln["units"], round(ln["allowed"] * 1.2, 2),
                     ln["allowed"], ln["allowed"], "11"),
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
                (case_id, case_number, seq, claim_id, detector, lob, org_id, member_id,
                 analyst_id, status, "post_pay", 1, priority, priority_score, 0,
                 amount, "offset" if amount >= 500 else "invoice",
                 identified_date.isoformat(), deadline_date.isoformat(), breached,
                 (date.fromisoformat(svc) - timedelta(days=365)).isoformat(), 0,
                 int(status == "pending_supervisor"), 0, 0,
                 json.dumps({"detector": detector, "profile": profile}),
                 json.dumps({"seq": seq}), NOW, NOW),
            )
            conn.execute(
                "INSERT INTO likelihood_scores (score_id, case_id, provider_risk_score, "
                "cpt_risk_score, dx_cpt_mismatch_score, claim_complexity_score, "
                "billing_variance_score, composite_likelihood, urgency_factor, "
                "urgency_override_applied, priority_score, score_json, scored_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (str(uuid4()), case_id, score or 0.3, 0.0, 0.0, 0.0, score or 0.3,
                 score or 0.3, 0.5, 0, priority_score, json.dumps({}), NOW),
            )
            finding_id = str(uuid4())
            conn.execute(
                "INSERT INTO findings (finding_id, claim_id, detector_id, detector_version, "
                "fired_at, overpayment_amount, severity, confidence, title, rationale, "
                "evidence, status, fwa_indicator) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (finding_id, claim_id, detector, "v1", NOW, amount, "high", 0.85,
                 f"{detector} overpayment", "Synthetic capacity-demo finding.",
                 json.dumps({"financial_impact": True}), "open", 0),
            )
            conn.execute("INSERT INTO case_findings (case_id, finding_id) VALUES (?,?)",
                         (case_id, finding_id))
            inserted += 1

        conn.commit()
        open_total = conn.execute(
            "SELECT COUNT(*) FROM opa_cases WHERE status NOT LIKE 'closed_%'"
        ).fetchone()[0]
        print(f"    Inserted {inserted} {CASE_PREFIX}* open cases; profiles: "
              + ", ".join(f"{k}={v}" for k, v in sorted(prof_counts.items())))
        print(f"    Open cases now total: {open_total}")
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_N
    run(n=n)
