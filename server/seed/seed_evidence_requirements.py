"""Seed evidence_requirements with a starter set covering high-yield
overpayment-recovery categories.

These rules are pedagogical/illustrative — real production deployments
should sync this table from CMS LCD/NCD, the NCCI Manual, and payer-
specific medical policy databases on a scheduled refresh."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW = datetime.utcnow().isoformat()


# (code_type, code, required_evidence, policy_reference, severity_if_missing, notes)
RULES = [
    # ── Modifier substantiation (NCCI Manual Ch. I) ────────────────────────
    ("modifier", "25",
     "Documentation of a significant, separately identifiable Evaluation and "
     "Management (E/M) service above and beyond the usual pre- and post-op "
     "work of the procedure performed on the same day. The E/M must have a "
     "distinct chief complaint, history, and assessment.",
     "NCCI Policy Manual, Chapter I; CPT Guidelines",
     "critical",
     "Modifier-25 abuse is one of the most-cited PI findings."),

    ("modifier", "59",
     "Documentation that the procedure is distinct or independent from other "
     "services performed on the same day — different session, different "
     "procedure, different site, or separate injury.",
     "NCCI Policy Manual, Chapter I",
     "critical",
     "Often misused to unbundle. Look for explicit site/session separation."),

    ("modifier", "GA",
     "ABN (Advance Beneficiary Notice) signed by the beneficiary on file "
     "before the service was rendered.",
     "CMS Pub. 100-04, Chapter 30",
     "warning",
     "ABN-related modifier."),

    # ── Orthopedic joint replacement ──────────────────────────────────────
    ("cpt", "27447",
     "Operative report documenting total knee arthroplasty; preoperative "
     "imaging showing osteoarthritis or other indication; documentation of "
     "failed conservative management (PT, NSAIDs, injections) for at least "
     "3-6 months.",
     "CMS LCD L33518 (Major Joint Replacement)",
     "critical",
     "High-dollar inpatient procedure."),

    ("cpt", "27130",
     "Operative report documenting total hip arthroplasty; preoperative "
     "imaging confirming OA or AVN; documentation of failed conservative "
     "management; functional limitation assessment.",
     "CMS LCD L33518 (Major Joint Replacement)",
     "critical",
     None),

    ("drg", "470",
     "Operative report for the joint replacement; H&P documenting the "
     "indication; absence of major complication/comorbidity (MCC) that would "
     "shift to DRG 469.",
     "CMS MS-DRG Definitions Manual v41",
     "critical",
     "Major joint replacement of lower extremity w/o MCC."),

    ("drg", "469",
     "Same operative documentation as DRG 470 plus documented MCC (e.g. "
     "sepsis, acute renal failure, acute MI) per the MS-DRG MCC list.",
     "CMS MS-DRG Definitions Manual v41",
     "critical",
     "MCC presence is the upcoding risk vs DRG 470."),

    # ── Cardiology ─────────────────────────────────────────────────────────
    ("cpt", "93306",
     "The actual echocardiogram report including 2D imaging, spectral and "
     "color flow Doppler interpretation, with chamber sizes, wall motion, "
     "and valve assessment.",
     "CMS NCD 220.5 (Echocardiography)",
     "critical",
     None),

    ("cpt", "93000",
     "ECG tracing on file with interpretation and report by the billing "
     "physician.",
     "CPT Guidelines; CMS Manual",
     "warning",
     None),

    ("drg", "247",
     "Cath lab report documenting percutaneous coronary intervention with "
     "drug-eluting stent placement; medical necessity (acute coronary "
     "syndrome, refractory angina, etc.); device implant log.",
     "CMS MS-DRG Definitions Manual v41",
     "critical",
     "Percutaneous cardiovascular procedures w/ drug-eluting stent w/o MCC."),

    # ── E/M codes ──────────────────────────────────────────────────────────
    ("cpt", "99213",
     "Office/outpatient established-patient E/M documentation supporting "
     "low-to-moderate complexity: chief complaint, expanded problem-focused "
     "history, expanded examination, and low-complexity MDM — OR time "
     "totaling 20-29 minutes on date of encounter.",
     "AMA CPT 2021 E/M Guidelines",
     "warning",
     None),

    ("cpt", "99214",
     "Office/outpatient established-patient E/M documentation supporting "
     "moderate complexity: detailed history, detailed examination, and "
     "moderate-complexity MDM — OR time totaling 30-39 minutes on date of "
     "encounter.",
     "AMA CPT 2021 E/M Guidelines",
     "warning",
     "Upcoding from 99213 is a frequent PI finding."),

    ("cpt", "99285",
     "Emergency department E/M documentation supporting high-complexity MDM "
     "or time-based criteria, with documented urgency or threat to life/limb.",
     "AMA CPT E/M Guidelines",
     "warning",
     None),

    # ── Chemotherapy / J-codes ─────────────────────────────────────────────
    ("cpt", "96413",
     "Documentation of the chemotherapy infusion: drug name, dose, route, "
     "duration (start and stop times), and infusion nurse/MD presence.",
     "CMS NCCI Manual, Chapter X",
     "critical",
     None),

    ("hcpcs", "J1745",
     "Documentation of Remicade (infliximab) administration: dose in mg, "
     "route, infusion duration, and NDC. Units billed must match dose given "
     "(1 unit = 10 mg).",
     "CMS Pub. 100-02, Chapter 15; HCPCS Level II Code Description",
     "critical",
     "Unit-quantity mismatch is a common overpayment vector for J-codes."),

    ("hcpcs", "J9035",
     "Documentation of Avastin (bevacizumab) administration: dose in mg, "
     "route, infusion duration, NDC, and approved indication. Units billed "
     "must match dose given (1 unit = 10 mg).",
     "CMS Pub. 100-02, Chapter 15",
     "critical",
     None),

    # ── Pulmonology ────────────────────────────────────────────────────────
    ("icd10", "J44.9",
     "Pulmonary function test (PFT) results, smoking history, and clinical "
     "presentation documented in the chart consistent with chronic "
     "obstructive pulmonary disease.",
     "CMS LCD L33457 (Pulmonary Function Testing)",
     "warning",
     None),

    # ── Imaging ────────────────────────────────────────────────────────────
    ("cpt", "70553",
     "MRI brain with and without contrast report; documented clinical "
     "indication (e.g. neurologic deficit, suspected mass); contrast "
     "administration record.",
     "CMS NCD 220.2 (MRI)",
     "warning",
     None),
]


def run(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    try:
        existing = conn.execute("SELECT COUNT(*) FROM evidence_requirements").fetchone()[0]
        if existing:
            print(f"  evidence_requirements already populated ({existing} rows) — skipping")
            return
        for code_type, code, req, ref, sev, notes in RULES:
            conn.execute(
                "INSERT INTO evidence_requirements ("
                "requirement_id, code_type, code, required_evidence, "
                "policy_reference, severity_if_missing, notes, is_active, "
                "created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (str(uuid4()), code_type, code, req, ref, sev, notes, 1, NOW, NOW),
            )
        conn.commit()
        print(f"  Seeded {len(RULES)} evidence_requirements rules")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
