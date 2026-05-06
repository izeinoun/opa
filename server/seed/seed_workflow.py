"""Seed workflow objects — synchronous sqlite3.

Creates:
  - AuditLog rows for all case status transitions
  - 12 Dispute rows (cases 41-52, pending_dispute status)
  - 20 ProviderNotice rows (cases with pending_provider_response)
  - 35 RecoupmentAction rows (cases that are closed_recovered or in_review)
  - 35 Reconciliation rows matching the recoupment actions
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW_DT  = datetime(2024, 6, 1, 8, 0, 0)
NOW     = NOW_DT.isoformat()

# Status transition chains per final status
STATUS_CHAINS = {
    "identified":               ["identified"],
    "in_review":                ["identified", "in_review"],
    "pending_provider_response":["identified", "in_review", "pending_provider_response"],
    "pending_dispute":          ["identified", "in_review", "pending_provider_response", "pending_dispute"],
    "closed_recovered":         ["identified", "in_review", "pending_provider_response", "closed_recovered"],
    "closed_unrecoverable":     ["identified", "in_review", "closed_unrecoverable"],
}

DISPUTE_REASONS = [
    ("DR-01", "Services were medically necessary as documented in the attached medical records."),
    ("DR-02", "The CPT code billed accurately reflects the complexity of the service rendered."),
    ("DR-03", "Prior authorization was obtained verbally; attached confirmation number for reference."),
    ("DR-04", "Modifier usage was appropriate per CMS bundling guidelines for the date of service."),
    ("DR-05", "The units billed correspond to the total service time documented in the chart notes."),
    ("DR-06", "Payment was based on the correct contracted rate for this provider specialty and LOB."),
]

DISPUTE_CHANNELS = ["mail", "fax", "portal", "phone"]
DISPUTE_STATUSES = ["open", "under_review", "upheld", "overturned"]


def _ts(base_dt: datetime, offset_days: int, hour: int = 9) -> str:
    dt = base_dt + timedelta(days=offset_days)
    return dt.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def run(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    try:
        if conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]:
            print("  audit_logs already seeded — skipping")
            return

        # ── Load reference data ───────────────────────────────────────────
        cases = conn.execute(
            "SELECT case_id, case_number, case_sequence, status, "
            "identified_date, lob, provider_org_id, total_overpayment_amount, "
            "recommended_recovery_method, claim_id FROM opa_cases ORDER BY case_sequence"
        ).fetchall()
        case_cols = ["case_id","case_number","case_sequence","status",
                     "identified_date","lob","provider_org_id",
                     "total_overpayment_amount","recommended_recovery_method","claim_id"]
        cases = [dict(zip(case_cols, row)) for row in cases]

        users = conn.execute(
            "SELECT user_id, username, role FROM opa_users"
        ).fetchall()
        user_map = {row[1]: row[0] for row in users}
        analyst_ids = [row[0] for row in users if row[2] == "analyst"]
        supervisor_id = next((row[0] for row in users if row[2] == "supervisor"), analyst_ids[0])
        system_id     = user_map.get("system.bot", analyst_ids[0])

        templates = conn.execute(
            "SELECT template_id, lob FROM letter_templates"
        ).fetchall()
        tmpl_by_lob = {row[1]: row[0] for row in templates}

        era_txns = conn.execute(
            "SELECT c.claim_id, t.transaction_id, p.payment_id "
            "FROM opa_cases oc "
            "JOIN claims c ON c.claim_id = oc.claim_id "
            "JOIN transactions_835 t ON c.era_transaction_id = t.transaction_id "
            "JOIN claim_payments_835 p ON p.transaction_id = t.transaction_id "
            "            AND p.claim_icn = c.icn "
            "WHERE oc.status = 'closed_recovered'"
        ).fetchall()
        era_by_claim = {row[0]: (row[1], row[2]) for row in era_txns}

        # ── Audit logs ────────────────────────────────────────────────────
        audit_count = 0
        for c in cases:
            chain = STATUS_CHAINS.get(c["status"], ["identified"])
            identified_dt = datetime.fromisoformat(c["identified_date"])
            actor = analyst_ids[(c["case_sequence"] - 1) % len(analyst_ids)]

            for step_idx, to_state in enumerate(chain):
                from_state = chain[step_idx - 1] if step_idx > 0 else None
                offset = step_idx * 3  # each transition ~3 days apart
                conn.execute(
                    "INSERT INTO audit_logs "
                    "(audit_id, case_id, actor_user_id, action, from_state, to_state, "
                    "reason, meta_json, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        str(uuid4()),
                        c["case_id"],
                        actor if step_idx > 0 else system_id,
                        f"status_change" if step_idx > 0 else "case_created",
                        from_state,
                        to_state,
                        f"Automated detector trigger" if step_idx == 0 else f"Analyst review — advancing to {to_state}",
                        json.dumps({"step": step_idx, "sequence": c["case_sequence"]}),
                        _ts(identified_dt, offset),
                    ),
                )
                audit_count += 1

        # ── Disputes (12) ─────────────────────────────────────────────────
        dispute_cases = [c for c in cases if c["status"] == "pending_dispute"][:12]
        dispute_count = 0
        for i, c in enumerate(dispute_cases):
            reason_code, reason_text = DISPUTE_REASONS[i % len(DISPUTE_REASONS)]
            channel = DISPUTE_CHANNELS[i % len(DISPUTE_CHANNELS)]
            d_status = DISPUTE_STATUSES[i % len(DISPUTE_STATUSES)]
            identified_dt = datetime.fromisoformat(c["identified_date"])
            received = _ts(identified_dt, 18)

            resolution_date = None
            resolution_notes = None
            resolved_by = None
            if d_status in ("upheld", "overturned"):
                resolution_date = _ts(identified_dt, 30)[:10]
                resolution_notes = (
                    "Provider documentation reviewed. Overpayment upheld — billing exceeded contracted rate."
                    if d_status == "upheld"
                    else "Provider documentation accepted. Determination reversed — medical necessity confirmed."
                )
                resolved_by = supervisor_id

            conn.execute(
                "INSERT INTO disputes "
                "(dispute_id, case_id, received_date, submitted_by_name, channel, "
                "dispute_reason_code, dispute_reason_text, supporting_evidence_ref, "
                "status, resolution_date, resolution_notes, resolved_by_user_id, "
                "created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()), c["case_id"],
                    received[:10],
                    f"Provider Relations — {c['case_number']}",
                    channel, reason_code, reason_text,
                    f"DOCS-{c['case_number']}.pdf",
                    d_status, resolution_date, resolution_notes, resolved_by,
                    received, received,
                ),
            )
            dispute_count += 1

        # ── Provider Notices (20) ─────────────────────────────────────────
        notice_cases = [c for c in cases if c["status"] == "pending_provider_response"][:20]
        notice_count = 0
        for i, c in enumerate(notice_cases):
            lob = c["lob"]
            template_id = tmpl_by_lob.get(lob, tmpl_by_lob.get("MA", "TMPL-MA-001"))
            identified_dt = datetime.fromisoformat(c["identified_date"])
            generated_at = _ts(identified_dt, 5)
            approved_at  = _ts(identified_dt, 6)
            sent_at      = _ts(identified_dt, 7)

            # Simple template render with dummy values
            letter = (
                f"Case: {c['case_number']} | LOB: {lob} | "
                f"Amount: ${c['total_overpayment_amount']:.2f} | "
                f"Recovery: {c['recommended_recovery_method']}"
            )

            conn.execute(
                "INSERT INTO provider_notices "
                "(notice_id, case_id, template_id, lob, generated_at, letter_content, "
                "status, approved_by_user_id, approved_at, sent_at, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()), c["case_id"], template_id, lob,
                    generated_at, letter, "sent",
                    supervisor_id, approved_at, sent_at,
                    generated_at, generated_at,
                ),
            )
            notice_count += 1

        # ── Recoupments + Reconciliations (35 each) ───────────────────────
        recoup_cases = (
            [c for c in cases if c["status"] == "closed_recovered"][:25]
            + [c for c in cases if c["status"] == "in_review"][:10]
        )
        recoup_count = 0
        recon_count  = 0
        for i, c in enumerate(recoup_cases[:35]):
            identified_dt = datetime.fromisoformat(c["identified_date"])
            submitted_at  = _ts(identified_dt, 10)
            confirmed_at  = _ts(identified_dt, 15) if c["status"] == "closed_recovered" else None
            r_status      = "confirmed" if c["status"] == "closed_recovered" else "submitted"
            amount        = c["total_overpayment_amount"]

            era_txn_id, era_pay_id = era_by_claim.get(c.get("claim_id", ""), (None, None))

            staging = {
                "case_number":   c["case_number"],
                "lob":           c["lob"],
                "amount":        amount,
                "method":        c["recommended_recovery_method"],
                "batch_id":      f"BATCH-2024-{i + 1:04d}",
                "exported_at":   submitted_at,
            }

            recoup_id = str(uuid4())
            conn.execute(
                "INSERT INTO recoupment_actions "
                "(recoupment_id, case_id, method, requested_amount, status, "
                "submitted_at, confirmed_at, recovery_835_transaction_id, "
                "staging_output_json, staging_status, staging_exported_at, "
                "created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    recoup_id, c["case_id"],
                    c["recommended_recovery_method"],
                    amount, r_status,
                    submitted_at, confirmed_at,
                    era_txn_id if c["status"] == "closed_recovered" else None,
                    json.dumps(staging),
                    "exported" if c["status"] == "closed_recovered" else "pending",
                    submitted_at if c["status"] == "closed_recovered" else None,
                    submitted_at, submitted_at,
                ),
            )
            recoup_count += 1

            # Reconciliation
            match_type = "full_match" if c["status"] == "closed_recovered" else "pending"
            reconciled_at = confirmed_at if c["status"] == "closed_recovered" else None
            actual_amount = amount if c["status"] == "closed_recovered" else None

            conn.execute(
                "INSERT INTO reconciliations "
                "(reconciliation_id, case_id, expected_amount, actual_amount, "
                "match_type, recovery_835_transaction_id, recovery_835_payment_id, "
                "plb_reference, treasury_reference, exception_reason, "
                "reconciled_at, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()), c["case_id"],
                    amount, actual_amount, match_type,
                    era_txn_id if c["status"] == "closed_recovered" else None,
                    era_pay_id if c["status"] == "closed_recovered" else None,
                    f"PLB-{i + 1:04d}" if c["status"] == "closed_recovered" else None,
                    f"TRS-{i + 1:06d}" if c["status"] == "closed_recovered" else None,
                    None,
                    reconciled_at,
                    submitted_at, submitted_at,
                ),
            )
            recon_count += 1

        conn.commit()
        print(f"  Inserted {audit_count} audit logs, {dispute_count} disputes, "
              f"{notice_count} notices, {recoup_count} recoupments, {recon_count} reconciliations")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
