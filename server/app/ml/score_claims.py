"""score_claims.py — run the Stage 2 Claim Predictor over real claims.

For every claim: assemble the five features (P_risk from the rendering provider's
calibrated Stage 1 score, F4/F5/F7/F8 from the claim's service lines with the
fee-schedule term joined from fee_schedules), score with the calibrated Stage 2
model, and write the result to claims.overpayment_probability.

Sync + sqlite, mirroring train_billing_variance.write_scores_to_db, so it runs
inside the seed pass. Missing provider score → P_risk defaults to 0.5 (spec §6);
missing fee-schedule row → that line contributes 0 to F5.
"""
from __future__ import annotations

import os
import sqlite3
from typing import Optional

from .stage2_features import compute_features
from .train_claim_predictor import score_claim, artifact_exists

_DEFAULT_P_RISK = 0.5


def _fee_amount(conn: sqlite3.Connection, org_id: Optional[str], lob: Optional[str],
                cpt: Optional[str], units: float) -> Optional[float]:
    """Fee-schedule amount = base_rate × units, from the matching fee_schedules row."""
    if not (org_id and cpt):
        return None
    row = conn.execute(
        "SELECT base_rate FROM fee_schedules "
        "WHERE provider_org_id=? AND cpt_code=? AND (lob=? OR ? IS NULL) "
        "ORDER BY (lob=?) DESC LIMIT 1",
        (org_id, cpt, lob, lob, lob),
    ).fetchone()
    if not row or row[0] is None:
        return None
    return float(row[0]) * max(units, 1.0)


def run(db_path: Optional[str] = None) -> int:
    """Score every claim; return the number updated. No-op if the artifact is
    missing (leaves probabilities NULL → funnel falls back to provider score)."""
    db_path = db_path or os.getenv("DB_PATH", "./opa.db")
    if not artifact_exists():
        print("  [score_claims] no claim_predictor artifact — skipping")
        return 0

    conn = sqlite3.connect(db_path)
    try:
        # provider RF score + specialty, keyed by NPI
        prov = {
            npi: (score, specialty)
            for npi, score, specialty in conn.execute(
                "SELECT npi, billing_variance_score, specialty FROM providers"
            ).fetchall()
        }
        claims = conn.execute(
            "SELECT claim_id, rendering_provider_npi, provider_org_id, lob FROM claims"
        ).fetchall()

        updated = 0
        for claim_id, npi, org_id, lob in claims:
            score, specialty = prov.get(npi, (None, None))
            p_risk = float(score) if score is not None else _DEFAULT_P_RISK

            line_rows = conn.execute(
                "SELECT cpt_code, modifier_1, modifier_2, units_billed, allowed_amount "
                "FROM claim_lines WHERE claim_id=?", (claim_id,)
            ).fetchall()
            lines = []
            for cpt, m1, m2, units, allowed in line_rows:
                u = float(units or 1.0)
                lines.append({
                    "cpt_code": cpt, "modifier_1": m1, "modifier_2": m2,
                    "units": u, "allowed_amount": float(allowed or 0.0),
                    "fee_schedule_amount": _fee_amount(conn, org_id, lob, cpt, u),
                })

            feats = compute_features(p_risk, lines, specialty)
            prob = score_claim(feats)
            conn.execute(
                "UPDATE claims SET overpayment_probability=? WHERE claim_id=?",
                (round(float(prob), 4), claim_id),
            )
            updated += 1

        conn.commit()
        print(f"  [score_claims] scored {updated} claims with the Stage 2 predictor")
        return updated
    finally:
        conn.close()


if __name__ == "__main__":
    run()
