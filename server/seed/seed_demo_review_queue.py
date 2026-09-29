"""seed_demo_review_queue.py — stage a fixed set of cases in Rachel Burns's Review
queue, WITH a coherent, transparent audit trail (including LLM decisions).

ADDITIVE and IDEMPOTENT for a curated demo set. It:
  1. Forces the six demo cases into `in_review`, assigned to Rachel Burns.
  2. Rebuilds their audit trail so it reads organically after a data reset:
        CASE_CREATED  →  LLM_EVALUATION:DET-xx (for each LLM-backed finding)
                      →  CASE_ASSIGNED (to Rachel)  →  STATUS_TRANSITION (in_review)
     The LLM rows put the model's actual decision text in `reason`, which is the
     field the case-detail UI renders — so the AI reasoning is visible in the
     timeline, not hidden in metadata (full transparency for an AI-expert demo).

Idempotent: it OWNS the audit trail for these six curated cases — it deletes their
existing audit rows and rewrites a deterministic set (timestamps derived from each
case's identified_date), so re-running produces the identical trail with no dupes.
It only ever touches the six listed case_ids.

Must run AFTER every case seeder, including seed_low_evidence_demo_case (00021).
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")

REVIEWER_USERNAME = "rachel.burns"
BOT_USERNAME = "system.bot"
LLM_MODEL_LABEL = "Claude (Anthropic)"

# LLM-backed detectors (they call the Anthropic SDK to reason about the claim).
LLM_DETECTORS = {"DET-09", "DET-18", "DET-19"}

CASE_NUMBERS = [
    "OPA-2026-00015",
    "OPA-2026-00013",
    "OPA-2026-00009",
    "OPA-2026-00021",
    "OPA-2026-00004",
    "OPA-2026-00020",
]


def _user_id(conn: sqlite3.Connection, username: str) -> str | None:
    row = conn.execute(
        "SELECT user_id FROM opa_users WHERE username = ?", (username,)
    ).fetchone()
    return row[0] if row else None


def _audit_row(conn, case_id, claim_id, actor, action, frm, to, reason, when, meta=None):
    conn.execute(
        "INSERT INTO audit_logs (audit_id, case_id, claim_id, actor_user_id, action, "
        "from_state, to_state, reason, meta_json, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (str(uuid4()), case_id, claim_id, actor, action, frm, to, reason,
         json.dumps(meta or {}), when),
    )


def run(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    try:
        reviewer_id = _user_id(conn, REVIEWER_USERNAME)
        bot_id = _user_id(conn, BOT_USERNAME) or reviewer_id
        if not reviewer_id:
            print(f"    Skipping demo review queue: user {REVIEWER_USERNAME!r} not seeded yet")
            return

        now = datetime.now().isoformat()
        placeholders = ",".join("?" * len(CASE_NUMBERS))
        cur = conn.execute(
            f"UPDATE opa_cases SET status='in_review', assigned_analyst_id=?, "
            f"is_active=1, updated_at=? WHERE case_number IN ({placeholders})",
            [reviewer_id, now, *CASE_NUMBERS],
        )
        print(f"    Staged {cur.rowcount}/{len(CASE_NUMBERS)} cases → in_review, "
              f"assigned to {REVIEWER_USERNAME}")

        audit_rows = 0
        llm_rows = 0
        for cn in CASE_NUMBERS:
            case = conn.execute(
                "SELECT case_id, claim_id, identified_date FROM opa_cases WHERE case_number=?",
                (cn,),
            ).fetchone()
            if not case:
                print(f"    (note: {cn} not found — skipped)")
                continue
            case_id, claim_id, identified = case

            # Own this case's audit trail: clear then rewrite deterministically.
            conn.execute("DELETE FROM audit_logs WHERE case_id = ?", (case_id,))

            try:
                d0 = date.fromisoformat((identified or "2026-06-01")[:10])
            except ValueError:
                d0 = date(2026, 6, 1)
            t_created = f"{d0.isoformat()}T08:00:00"
            t_assigned = f"{(d0 + timedelta(days=2)).isoformat()}T09:00:00"
            t_review = f"{(d0 + timedelta(days=2)).isoformat()}T09:15:00"

            # 1. Case created by the detector run.
            _audit_row(conn, case_id, claim_id, bot_id, "CASE_CREATED", None, "new",
                       "Overpayment identified by automated detector run", t_created)
            audit_rows += 1

            # 2. LLM evaluations — one row per LLM-backed finding, decision text in `reason`.
            llm_findings = conn.execute(
                "SELECT detector_id, confidence, rationale FROM findings "
                "WHERE claim_id = ? AND detector_id IN (%s) ORDER BY detector_id"
                % ",".join("?" * len(LLM_DETECTORS)),
                (claim_id, *sorted(LLM_DETECTORS)),
            ).fetchall()
            for i, (det, conf, rationale) in enumerate(llm_findings):
                reason = (
                    f"LLM evaluation via {LLM_MODEL_LABEL} — flagged as a likely "
                    f"overpayment (confidence {float(conf or 0):.0%}). "
                    f"Reasoning: {rationale or 'clinical-coding mismatch identified'}"
                )
                when = f"{d0.isoformat()}T08:{5 + i:02d}:00"
                _audit_row(conn, case_id, claim_id, bot_id, f"LLM_EVALUATION:{det}",
                           "new", "new", reason, when,
                           meta={"model": LLM_MODEL_LABEL, "detector": det,
                                 "confidence": conf, "decision": "flag_overpayment"})
                audit_rows += 1
                llm_rows += 1

            # 3. Analyst pulls the case from intake.
            _audit_row(conn, case_id, claim_id, reviewer_id, "CASE_ASSIGNED", "new", "assigned",
                       "Picked up from the intake queue — assigned to Rachel Burns", t_assigned,
                       meta={"assignee_id": reviewer_id})
            audit_rows += 1

            # 4. Analyst opens the review.
            _audit_row(conn, case_id, claim_id, reviewer_id, "STATUS_TRANSITION",
                       "assigned", "in_review", "Moved to review by Rachel Burns", t_review)
            audit_rows += 1

        conn.commit()
        print(f"    Rebuilt audit trail: {audit_rows} rows ({llm_rows} LLM-evaluation "
              f"entries) across {len(CASE_NUMBERS)} cases")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
