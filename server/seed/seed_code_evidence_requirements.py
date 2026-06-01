"""Seed common ICD-10 and DRG evidence requirements.

The evidence scanner reads `is_active=True` rows from this table to determine
which medical-record evidence to look for on each claim. Customers can edit
or add to this via the admin UI later.

This is a small but representative starter set focused on high-dollar,
high-audit-risk codes where pre-pay review most often catches documentation
gaps in real-world payment integrity work.
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "./opa.db")


# (code_type, code, title, requirement_description)
SEED_REQUIREMENTS: list[tuple[str, str, str, str]] = [
    # ── ICD-10 ─────────────────────────────────────────────────────────────
    (
        "icd10", "A41.9", "Sepsis, unspecified organism",
        "Look for evidence of SIRS criteria (at least two of: fever, tachycardia, "
        "tachypnea, leukocytosis) PLUS documented or suspected source of infection. "
        "Look for blood culture results, lactate level, antibiotic orders, and "
        "physician documentation explicitly stating 'sepsis' or 'septic'."
    ),
    (
        "icd10", "I50.21", "Acute systolic (congestive) heart failure",
        "Look for symptoms (dyspnea, orthopnea, edema), an echo or BNP/NT-proBNP "
        "result, and a physician note explicitly distinguishing acute systolic "
        "(reduced EF) from diastolic. Treatment with IV diuretics or new heart-"
        "failure medications also supports acute decompensation."
    ),
    (
        "icd10", "I21.4", "Non-ST elevation myocardial infarction (NSTEMI)",
        "Look for elevated cardiac troponin (with serial measurements), EKG "
        "findings consistent with NSTEMI (ST depression or T-wave inversion, "
        "no ST elevation), and chest pain or anginal-equivalent symptoms. "
        "Cardiology consult notes strengthen the documentation."
    ),
    (
        "icd10", "J44.1", "COPD with (acute) exacerbation",
        "Look for documented baseline COPD plus acute worsening of dyspnea, "
        "cough, or sputum production. Treatment with systemic corticosteroids, "
        "bronchodilators beyond baseline, or antibiotics supports acute "
        "exacerbation. Pulmonary function tests or prior COPD history strengthen the case."
    ),
    (
        "icd10", "N17.9", "Acute kidney injury, unspecified",
        "Look for serum creatinine rise (≥0.3 mg/dL within 48h or ≥1.5x baseline "
        "within 7 days) or oliguria (<0.5 mL/kg/h for >6h). Documentation should "
        "contrast against patient's recent baseline creatinine."
    ),
    (
        "icd10", "E11.9", "Type 2 diabetes mellitus without complications",
        "Look for fasting glucose ≥126 mg/dL, HbA1c ≥6.5%, random glucose ≥200 "
        "with symptoms, or documented history with current diabetes medication. "
        "Distinguish from Type 1 (E10.x) by patient age of onset and insulin dependence."
    ),
    (
        "icd10", "G93.1", "Anoxic brain damage, not elsewhere classified",
        "Look for documented hypoxic or anoxic event (cardiac arrest, drowning, "
        "asphyxia) and neurological findings consistent with brain injury. "
        "Imaging (MRI/CT) or neurology consult notes support the diagnosis."
    ),
    (
        "icd10", "K56.60", "Unspecified intestinal obstruction",
        "Look for imaging (CT or X-ray) showing dilated bowel loops, air-fluid "
        "levels, or transition point. Clinical symptoms include abdominal pain, "
        "distension, nausea/vomiting, and obstipation. NG tube placement or "
        "surgical consult supports acuity."
    ),
    (
        "icd10", "R65.20", "Severe sepsis without septic shock",
        "Look for sepsis diagnosis (see A41.9) PLUS evidence of organ dysfunction "
        "(elevated lactate, oliguria, acute respiratory failure, altered mental "
        "status, coagulopathy). Should NOT have documented hypotension requiring "
        "vasopressors (that's R65.21 septic shock)."
    ),
    (
        "icd10", "M17.11", "Unilateral primary osteoarthritis, right knee",
        "Look for imaging confirming osteoarthritic changes (joint space narrowing, "
        "osteophytes), failed conservative management (NSAIDs, physical therapy, "
        "intra-articular injections), and physical exam findings (pain on motion, "
        "crepitus, deformity)."
    ),
    # ── DRGs ───────────────────────────────────────────────────────────────
    (
        "drg", "470", "Major hip and knee joint replacement w/o MCC",
        "Look for failed conservative management (≥3 months of PT/NSAIDs/"
        "injections), imaging showing severe joint disease, surgical consent and "
        "pre-op clearance, and absence of major comorbidities/complications (if "
        "MCC present, should be DRG 469 instead)."
    ),
    (
        "drg", "291", "Heart failure & shock w/ MCC",
        "Look for principal diagnosis of acute heart failure (see I50.21 / "
        "I50.22 / I50.41) PLUS a documented major complication or comorbidity "
        "(MCC) — common MCCs include acute renal failure, respiratory failure, "
        "sepsis. Without an MCC this is DRG 292 or 293."
    ),
    (
        "drg", "871", "Septicemia or severe sepsis w/o MV >96 hrs w/ MCC",
        "Look for sepsis or severe sepsis diagnosis (see A41.9 / R65.20) plus "
        "an MCC. Mechanical ventilation, if present, must be ≤96 hours (otherwise "
        "DRG 870). Blood cultures, lactate trend, and antibiotic course should be documented."
    ),
    (
        "drg", "247", "Perc cardiovasc proc w/ drug-eluting stent w/o MCC",
        "Look for documented coronary artery disease with ≥70% stenosis on "
        "angiography, evidence of ischemia (positive stress test, NSTEMI, "
        "unstable angina), procedure note describing DES placement, and "
        "post-procedure dual antiplatelet therapy orders."
    ),
    (
        "drg", "194", "Simple pneumonia & pleurisy w/ CC",
        "Look for radiographic evidence of pneumonia (chest X-ray or CT), "
        "clinical signs (fever, cough, sputum, hypoxia), and a documented CC "
        "(comorbidity/complication) such as COPD, diabetes, or CHF. Antibiotic "
        "selection should align with community-acquired vs hospital-acquired distinction."
    ),
]


def run(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    try:
        existing = conn.execute(
            "SELECT COUNT(*) FROM code_evidence_requirements"
        ).fetchone()[0]
        if existing:
            print(f"  code_evidence_requirements already has {existing} rows — skipping")
            return

        now = datetime.utcnow().isoformat()
        for code_type, code, title, desc in SEED_REQUIREMENTS:
            conn.execute(
                "INSERT INTO code_evidence_requirements "
                "(requirement_id, code_type, code, title, requirement_description, "
                "is_active, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), code_type, code, title, desc, 1, now, now),
            )
        conn.commit()
        print(f"  Seeded {len(SEED_REQUIREMENTS)} code evidence requirements")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
