"""Seed pre-pay claims for the ClaimGuard "AI Findings" demo — synchronous sqlite3.

Creates a small, varied set of pipeline_mode='pre_pay' claims, faithfully
replicating what the intake service (app.services.prepay_intake_service.
ingest_extracted_claim) produces: PREPAY-YYYYMMDD-XXXXXXXX ICN, one claim_line
per CPT with even-split billed allocation, the same raw_claim_json envelope,
and the same field defaults (claim_status='pending', pos_code='11', etc.).

Raw sqlite3 (keyed on DB_PATH) — consistent with every other seed module, so a
custom DB_PATH stays authoritative.

Patient + provider names resolve against reference data seeded earlier
(seed_members / seed_providers); this step MUST run after those.

AI findings are NOT generated here — they're produced lazily and cached the
first time a claim's detail is opened (the app's lazy-AI design). Each seeded
claim therefore starts with zero findings until first viewed (or analyzed).

Idempotent: skips entirely if any pre-pay claim already exists.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")


def _dos(days_ago: int) -> str:
    return (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


# Each dict uses the same keys the intake service consumes. Patient + provider
# MUST match seeded members / provider_orgs (case-insensitive, exact name).
def _claim_specs() -> list[dict]:
    return [
        {
            "type": "CMS-1500", "claim_form": "Outpatient", "specialty": "Other",
            "provider": "Midwest Cardiac & Specialty Group",
            "patient": "Evelyn Kowalski", "dob": "1941-11-05", "dos": _dos(12),
            "billed_amount": 1240.00, "cpts": ["99215", "93306"],
            "icd10": ["I50.9", "I25.10"],
            "description": "Established-patient cardiology follow-up with transthoracic "
                           "echocardiogram for congestive heart failure.",
        },
        {
            "type": "UB-04", "claim_form": "Inpatient", "specialty": "Inpatient",
            "drg": "470", "provider": "Lakeside Multi-Specialty Associates",
            "patient": "Bernard Ostrowski", "dob": "1950-02-14", "dos": _dos(20),
            "billed_amount": 38500.00, "cpts": [],
            "icd10": ["M17.11", "Z96.651"],
            "description": "Inpatient total knee arthroplasty, right knee, two-day "
                           "length of stay.",
        },
        {
            "type": "CMS-1500", "claim_form": "Outpatient", "specialty": "Surgical",
            "provider": "North Shore Rehabilitation Network",
            "patient": "Mildred Reyes", "dob": "1947-06-07", "dos": _dos(14),
            "billed_amount": 28750.00, "cpts": ["27447", "01402"],
            "icd10": ["M17.12"],
            "description": "Outpatient left total knee arthroplasty with monitored "
                           "anesthesia care.",
        },
        {
            "type": "CMS-1500", "claim_form": "Outpatient", "specialty": "Oncology",
            "provider": "Midwest Cardiac & Specialty Group",
            "patient": "Harold Simmons", "dob": "1948-07-22", "dos": _dos(10),
            "billed_amount": 9820.00, "cpts": ["96413", "J9045"],
            "icd10": ["C34.90"],
            "description": "Chemotherapy infusion with carboplatin for malignant "
                           "neoplasm of the lung.",
        },
        {
            "type": "CMS-1500", "claim_form": "Outpatient", "specialty": "Other",
            "provider": "North Shore Rehabilitation Network",
            "patient": "Walter Pryor", "dob": "1952-04-18", "dos": _dos(7),
            "billed_amount": 2100.00, "cpts": ["99223"],
            "icd10": ["J18.9"],
            # Deliberate form-type mismatch: an inpatient initial-hospital E&M
            # billed on a CMS-1500. Exercises the "Incorrect Form Type" finding.
            "description": "Initial hospital inpatient evaluation and management, "
                           "high complexity, for pneumonia.",
        },
        {
            "type": "UB-04", "claim_form": "Outpatient", "specialty": "Other",
            "provider": "Lakeside Multi-Specialty Associates",
            "patient": "Ruth Chandler", "dob": "1944-09-30", "dos": _dos(17),
            "billed_amount": 640.00, "cpts": ["80053", "85025", "71046"],
            "icd10": ["R07.9", "E11.9"],
            "description": "Outpatient diagnostic labs and single-view chest "
                           "radiograph for chest-pain evaluation.",
        },
        {
            # Intentional CODE-VERSIONING demo: 99241 (office consultation) was DELETED
            # by CMS/AMA effective 2023-01-01. Billed here with a current date of service,
            # so DET-13 fires INACTIVE_CODE — "found in reference tables but inactive on
            # the date of service (terminated 2022-12-31)." Showcases date-of-service
            # code-lifecycle governance on purpose, using a genuinely retired code.
            "type": "CMS-1500", "claim_form": "Outpatient", "specialty": "Other",
            "provider": "Midwest Cardiac & Specialty Group",
            "patient": "Evelyn Kowalski", "dob": "1941-11-05", "dos": _dos(9),
            "billed_amount": 210.00, "cpts": ["99241"],
            "icd10": ["I10"],
            "description": "Office consultation billed with a consultation code (99241) "
                           "that CMS deleted effective 2023-01-01 — retired-code / "
                           "date-of-service versioning demonstration.",
        },
    ]


# ── normalizers (mirror prepay_intake_service) ──────────────────────────────

def _norm_form_type(v) -> str:
    return v if v in {"CMS-1500", "UB-04"} else "CMS-1500"


def _norm_care_setting(v, form_type: str) -> str:
    s = v or ("Inpatient" if form_type == "UB-04" else "Outpatient")
    return s if s in {"Inpatient", "Outpatient"} else "Outpatient"


def _norm_specialty(v) -> str:
    s = v or "Other"
    return s if s in {"Surgical", "Oncology", "Inpatient", "Other"} else "Other"


# ── reference resolution (raises on missing, like the service) ──────────────

def _resolve_member(conn: sqlite3.Connection, patient: str, dob: str | None):
    parts = (patient or "").strip().split(maxsplit=1)
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""
    sql = ("SELECT member_id, lob FROM members "
           "WHERE lower(first_name) = lower(?) AND lower(last_name) = lower(?)")
    args: list = [first, last]
    if dob:
        sql += " AND date_of_birth = ?"
        args.append(dob)
    sql += " ORDER BY member_id LIMIT 1"
    row = conn.execute(sql, args).fetchone()
    if not row:
        raise LookupError(f"member '{patient}' (DOB {dob}) not found")
    return row[0], (row[1] or "commercial")


def _resolve_provider(conn: sqlite3.Connection, provider: str):
    org = conn.execute(
        "SELECT provider_org_id FROM provider_orgs WHERE lower(name) = lower(?) LIMIT 1",
        [(provider or "").strip()],
    ).fetchone()
    if not org:
        raise LookupError(f"provider_org '{provider}' not found")
    org_id = org[0]
    prov = conn.execute(
        "SELECT npi FROM providers WHERE provider_org_id = ? LIMIT 1", [org_id]
    ).fetchone()
    if not prov:
        raise LookupError(f"provider_org '{provider}' has no providers")
    return org_id, prov[0]


def _insert_claim(conn: sqlite3.Connection, spec: dict) -> str:
    form_type = _norm_form_type(spec.get("type"))
    care_setting = _norm_care_setting(spec.get("claim_form"), form_type)
    specialty = _norm_specialty(spec.get("specialty"))
    billed = max(float(spec.get("billed_amount") or 0), 0.0)
    cpts = [str(c) for c in (spec.get("cpts") or []) if c]
    icd10 = [str(c) for c in (spec.get("icd10") or []) if c]
    dos = spec.get("dos") or datetime.utcnow().strftime("%Y-%m-%d")
    description = (spec.get("description") or "")[:1000]

    member_id, lob = _resolve_member(conn, str(spec.get("patient") or ""), spec.get("dob"))
    org_id, npi = _resolve_provider(conn, str(spec.get("provider") or ""))

    claim_id = str(uuid4())
    now = datetime.utcnow().isoformat()
    icn = f"PREPAY-{datetime.utcnow().strftime('%Y%m%d')}-{claim_id[:8].upper()}"

    conn.execute(
        """INSERT INTO claims (
            claim_id, icn, case_group_id, member_id, provider_org_id,
            billing_provider_npi, rendering_provider_npi, lob, pipeline_mode,
            service_from_date, service_to_date, claim_type, claim_form_type,
            care_setting, drg, specialty, description, extracted_text,
            claim_summary, code_descriptions, claim_status, total_billed,
            total_paid, paid_date, authorization_number, submission_date,
            pos_code, primary_icd, era_transaction_id, raw_claim_json,
            created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            claim_id, icn, None, member_id, org_id,
            npi, npi, lob, "pre_pay",
            dos, dos,
            "professional" if form_type == "CMS-1500" else "institutional",
            form_type, care_setting, spec.get("drg") or None, specialty,
            description, None, None, None, "pending", billed,
            None, None, None, now[:10],
            "11", icd10[0] if icd10 else "Z00.00", None,
            json.dumps({"source": "pdf_intake", "extracted": spec}),
            now, now,
        ),
    )

    if cpts:
        per_line = round(billed / len(cpts), 2)
        for i, code in enumerate(cpts, start=1):
            conn.execute(
                """INSERT INTO claim_lines (
                    claim_line_id, claim_id, line_number, cpt_code, service_date,
                    diag_1, diag_2, diag_3, diag_4,
                    modifier_1, modifier_2, units_billed, units_paid,
                    billed_amount, paid_amount, allowed_amount, pos_code, revenue_code
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(uuid4()), claim_id, i, code, dos,
                    icd10[0] if len(icd10) > 0 else None,
                    icd10[1] if len(icd10) > 1 else None,
                    icd10[2] if len(icd10) > 2 else None,
                    icd10[3] if len(icd10) > 3 else None,
                    None, None, 1, None, per_line, None, None, "11", None,
                ),
            )
    return claim_id


def _existing_prepay_count(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM claims WHERE pipeline_mode = 'pre_pay'"
    ).fetchone()[0]


def run(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    try:
        existing = _existing_prepay_count(conn)
        if existing:
            print(f"  pre-pay claims already present ({existing}); skipping")
            return
        created = 0
        for spec in _claim_specs():
            try:
                cid = _insert_claim(conn, spec)
                created += 1
                print(f"  + {spec['patient']:<20} {spec['type']:<8} "
                      f"${spec['billed_amount']:>9,.2f}  ({cid[:8]})")
            except LookupError as e:
                print(f"  ! skipped {spec['patient']}: {e}")
        conn.commit()
        print(f"  seeded {created} pre-pay claims "
              f"(AI findings generate lazily on first open)")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
