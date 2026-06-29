"""Seed performance dashboard data for Ana Chen.

Creates closed cases assigned to Ana Chen with various dispositions,
audit logs for closure, and recoupment actions to make her dashboard
interesting with recovered dollars, case closures, and pipeline stats.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4, uuid5
from typing import Optional

DB_PATH = os.getenv("DB_PATH", "./opa.db")
TODAY = date.today()

# Deterministic user ID for Ana Chen
_USER_NS = UUID("a1b2c3d4-0000-4000-8000-000000000001")
ANA_CHEN_ID = str(uuid5(_USER_NS, "ana.chen"))

# Case statuses that count as "closed" for dashboard
CLOSED_STATUSES = {
    "closed_recovered",
    "closed_written_off",
    "closed_overturned",
    "closed_no_overpayment",
    "closed_unrecoverable",
}

# Test case IDs we'll use (deterministic UUIDs based on index)
_CASE_NS = UUID("b2c3d4e5-0000-5000-9000-000000000001")

def case_id_for(index: int) -> str:
    """Generate deterministic case ID from index."""
    return str(uuid5(_CASE_NS, f"ana_perf_case_{index}"))


def run(db_path: str = DB_PATH) -> int:
    """Seed Ana Chen's performance data."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if already has closed cases (for performance dashboard)
        cursor.execute("SELECT COUNT(*) FROM opa_cases WHERE assigned_analyst_id = ? AND is_active = 0", (ANA_CHEN_ID,))
        closed_count = cursor.fetchone()[0]
        if closed_count > 0:
            print(f"  Ana Chen already has {closed_count} closed cases — skipping performance seed")
            return 0

        # We need existing claims and providers. Fetch some demo claim_ids with member_id.
        cursor.execute("""
            SELECT c.claim_id, c.provider_org_id, c.total_paid, c.member_id, c.lob
            FROM claims c
            WHERE c.pipeline_mode = 'post_pay'
            LIMIT 15
        """)
        available_claims = cursor.fetchall()

        if not available_claims:
            print("  No post-pay claims found — cannot seed performance data")
            return 0

        # Create cases with various statuses and closure dates across last 30/90 days
        cases_to_insert = []
        audit_logs_to_insert = []
        recoupment_to_insert = []

        for i, (claim_id, provider_org_id, paid_amount, member_id, lob) in enumerate(available_claims[:12]):
            case_id = case_id_for(i)

            # Vary statuses and recovery amounts
            if i % 5 == 0:
                status = "closed_recovered"
                recovery_pct = 0.70 + (i % 3) * 0.15  # 70-85%
            elif i % 5 == 1:
                status = "closed_written_off"
                recovery_pct = 0
            elif i % 5 == 2:
                status = "closed_overturned"
                recovery_pct = 0
            elif i % 5 == 3:
                status = "closed_no_overpayment"
                recovery_pct = 0
            else:
                status = "closed_unrecoverable"
                recovery_pct = 0

            # Spread closure dates across last 30 days (and some into 90 days)
            days_ago = 2 + (i * 2.5)  # Space them out
            closure_date = TODAY - timedelta(days=days_ago)

            # Overpayment amount (what was at-risk)
            overpayment = float(paid_amount or 1000) * (0.15 + i * 0.03 % 0.3)

            # Case identified date: 30-60 days before closure
            identified_date = closure_date - timedelta(days=30 + (i % 20))

            cases_to_insert.append((
                case_id,
                case_id.split('-')[0][:20],  # case_number (truncate to safe length)
                i + 1000,  # case_sequence
                claim_id,
                None,  # case_group_id
                "DET-04",  # primary_detector_id
                lob or "MA",  # lob
                provider_org_id,
                member_id,  # member_id
                ANA_CHEN_ID,  # assigned_analyst_id
                status,
                "post_pay",  # pipeline_mode
                False,  # is_active
                "MEDIUM",  # priority
                50.0,  # priority_score
                round(overpayment, 2),  # total_overpayment_amount
                0,  # review_time_minutes
                "request_recovery",  # recommended_recovery_method
                identified_date.isoformat(),  # identified_date
                (closure_date + timedelta(days=30)).isoformat(),  # deadline_date
                False,  # deadline_breached
                (identified_date - timedelta(days=90)).isoformat(),  # lookback_window_start
                None,  # provider_response_due_date
                False,  # is_sensitive_provider
                False,  # requires_supervisor_approval
                "[]",  # evidence_bundle (empty JSON array)
                "{}",  # case_json (empty JSON object)
                None,  # decision_metadata
                None,  # siu_investigation_id
                False,  # law_enforcement_hold
                False,  # siu_frozen
                datetime.now().isoformat(),  # created_at
                datetime.now().isoformat(),  # updated_at
                None,  # delivery_confirmation_ref
                None,  # last_delivery_attempt_at
            ))

            # Create audit log entry showing case closure
            audit_logs_to_insert.append((
                str(uuid4()),  # audit_id
                case_id,
                None,  # claim_id
                ANA_CHEN_ID,  # actor_user_id
                "STATUS_TRANSITION",  # action
                "open" if status != "closed_recovered" else "approved",  # from_state
                status,  # to_state
                f"Case closed as {status}",  # reason
                "{}",  # meta_json (empty object)
                closure_date.isoformat(),  # created_at
            ))

            # Add recoupment action if recovered
            if status == "closed_recovered" and recovery_pct > 0:
                recovered_amount = round(overpayment * recovery_pct, 2)
                recoupment_to_insert.append((
                    str(uuid4()),  # recoupment_id
                    case_id,
                    "request_recovery",  # method
                    recovered_amount,  # requested_amount
                    "confirmed",  # status
                    (closure_date - timedelta(days=5)).isoformat(),  # submitted_at
                    closure_date.isoformat(),  # confirmed_at
                    None,  # recovery_835_transaction_id
                    "{}",  # staging_output_json (empty object)
                    "pending",  # staging_status
                    None,  # staging_exported_at
                    datetime.now().isoformat(),  # created_at
                    datetime.now().isoformat(),  # updated_at
                ))

        # Insert cases
        cursor.executemany("""
            INSERT INTO opa_cases
            (case_id, case_number, case_sequence, claim_id, case_group_id, primary_detector_id,
             lob, provider_org_id, member_id, assigned_analyst_id, status, pipeline_mode,
             is_active, priority, priority_score, total_overpayment_amount, review_time_minutes,
             recommended_recovery_method, identified_date, deadline_date, deadline_breached,
             lookback_window_start, provider_response_due_date, is_sensitive_provider,
             requires_supervisor_approval, evidence_bundle, case_json, decision_metadata,
             siu_investigation_id, law_enforcement_hold, siu_frozen, created_at, updated_at,
             delivery_confirmation_ref, last_delivery_attempt_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, cases_to_insert)

        # Insert audit logs
        cursor.executemany("""
            INSERT INTO audit_logs
            (audit_id, case_id, claim_id, actor_user_id, action, from_state, to_state, reason, meta_json, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, audit_logs_to_insert)

        # Insert recoupment actions
        cursor.executemany("""
            INSERT INTO recoupment_actions
            (recoupment_id, case_id, method, requested_amount, status, submitted_at, confirmed_at,
             recovery_835_transaction_id, staging_output_json, staging_status, staging_exported_at,
             created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, recoupment_to_insert)

        conn.commit()

        recovered_count = len([r for r in recoupment_to_insert])
        print(f"  Inserted {len(cases_to_insert)} closed cases for Ana Chen")
        print(f"    - {recovered_count} recovered cases with recoupment actions")
        print(f"    - Closure dates: {(TODAY - timedelta(days=25)).isoformat()} to {TODAY.isoformat()}")

        return len(cases_to_insert)

    except Exception as e:
        print(f"  Error seeding Ana Chen performance data: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run()
