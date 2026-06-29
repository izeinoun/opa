"""
Migration: add CPT 31600/71045/90999/94002, HCPCS J0885/T1016,
           ICD-10 E11.65/J95.00/J96.11/N18.6, DRG 207
Run once from repo root: python migrate_add_reference_codes_20260627.py
"""
import os
import sqlite3
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW = "2026-06-27T00:00:00"
AMA_URL = "https://www.ama-assn.org/practice-management/cpt"
CMS_ICD_URL = "https://www.cms.gov/medicare/coding-billing/icd-10-codes"
CMS_DRG_URL = "https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps"
HCPCS_URL = "https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-coding-system-hcpcs-codes"

NEW_CPT_CODES = [
    ("31600", "Tracheotomy, planned (separate procedure)",
     "cpt", "high", 0.55, 1, True, "ENT/Pulmonology", False, 90,
     "2024-01-01", None,
     "Planned surgical tracheotomy — 90-day global period. Requires documented indication (prolonged mechanical ventilation, upper airway obstruction, or secretion management). Prior auth typically required. Verify operative note and anesthesia record. Flag if billed concurrently with 94002 on same day without documented separate necessity.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.95, "Pulled from AMA CPT 2025 tabular", "mandatory"),

    ("71045", "Radiologic examination, chest; single view",
     "cpt", "low", 0.10, 1, False, "Radiology", False, 0,
     "2024-01-01", None,
     "Single-view chest X-ray — high volume, low value. Flag when billed repeatedly without documented clinical indication. Verify split-billing (26/TC) when physician reads but does not own equipment. Common in ED and inpatient — ensure not duplicated across facility and professional claims.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.95, "Pulled from AMA CPT 2025 tabular", "mandatory"),

    ("90999", "Unlisted dialysis procedure, inpatient or outpatient",
     "cpt", "high", 0.50, 1, False, "Nephrology", False, 0,
     "2024-01-01", None,
     "Unlisted dialysis procedure — requires documentation of why no specific CPT applies. High audit risk due to non-specific nature; payers typically require manual review. Verify that a more specific dialysis code (90935, 90937, 90945, 90947, 90951-90970 series) does not describe the service performed.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.90, "Pulled from AMA CPT 2025 tabular", "mandatory"),

    ("94002", "Ventilation assist and management, initiation of pressure or volume preset ventilators for assisted or controlled breathing; hospital inpatient/observation, initial day",
     "cpt", "high", 0.60, 1, False, "Pulmonology/Critical Care", False, 0,
     "2024-01-01", None,
     "Mechanical ventilator initiation — inpatient initial day. Requires documented respiratory failure or acute indication for intubation (J96.11 acute respiratory failure, J95.00 VAP). Cannot be billed by same physician billing critical care (99291/99292) for same time period. Verify physician documented ventilator management separately from critical care service.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.95, "Pulled from AMA CPT 2025 tabular", "mandatory"),
]

NEW_HCPCS_CODES = [
    ("J0885", "Injection, epoetin alfa, (for non-ESRD use), per 1000 units",
     "hcpcs", "high", 0.45, 1, True, "Hematology/Nephrology", False, 0,
     "2024-01-01", None,
     "Epoetin alfa injection — prior auth required for non-ESRD use. CMS and commercial payers require documented anemia (Hgb threshold) and qualifying condition (e.g., chemotherapy-induced anemia, pre-surgery). Flag when billed without supporting CBC values or oncology/nephrology diagnosis. Dose should align with weight-based dosing guidelines; flag outlier units.",
     "CMS", "HCPCS 2025", HCPCS_URL, "2025-01-01", 0.95, "CMS HCPCS Level II 2025 tabular", "mandatory"),

    ("T1016", "Case management, each 15 minutes",
     "hcpcs", "moderate", 0.20, 4, False, "Care Management", False, 0,
     "2024-01-01", None,
     "Case management billed in 15-minute units — state Medicaid programs are primary payers; Medicare does not cover T-codes. Verify state Medicaid LCD/coverage policies apply. Flag when units exceed reasonable case management activity (>8 units/day suggests overbilling). Documentation must reflect actual case manager time spent on care coordination.",
     "CMS", "HCPCS 2025", HCPCS_URL, "2025-01-01", 0.90, "CMS HCPCS Level II 2025 tabular", "mandatory"),
]

NEW_ICD_CODES = [
    ("E11.65", "Type 2 diabetes mellitus with hyperglycemia",
     "icd10_cm", "moderate", "Endocrine, Nutritional and Metabolic Diseases", False, False,
     "both", True,
     "2024-10-01", None,
     "T2DM with active hyperglycemia — more specific than E11.9 (uncomplicated). Affects DRG CC severity in inpatient. Requires documented blood glucose elevation or symptomatic hyperglycemia in clinical notes. Flag if used solely to upcode DRG without supporting glucose documentation. Verify insulin or oral agent management is documented.",
     "CMS", "ICD-10-CM 2025", CMS_ICD_URL, "2025-01-01", 0.95, "CMS ICD-10-CM tabular", "mandatory"),

    ("J95.00", "Unspecified ventilator associated pneumonia",
     "icd10_cm", "high", "Diseases of the Respiratory System", False, False,
     "inpatient", True,
     "2024-10-01", None,
     "Ventilator-associated pneumonia (VAP) — hospital-acquired complication; CMS may not reimburse additional costs attributed to VAP as a HAC. Requires documented clinical criteria (new infiltrate on CXR, fever, leukocytosis, purulent secretions) in mechanically ventilated patient. Specify organism when identified (J95.01-J95.09). Flag if added without documented clinical VAP criteria — DRG upcoding concern.",
     "CMS", "ICD-10-CM 2025", CMS_ICD_URL, "2025-01-01", 0.95, "CMS ICD-10-CM tabular", "mandatory"),

    ("J96.11", "Acute respiratory failure with hypoxia",
     "icd10_cm", "high", "Diseases of the Respiratory System", False, False,
     "inpatient", True,
     "2024-10-01", None,
     "Acute respiratory failure with hypoxia — MCC in most DRGs; significantly elevates DRG weight. Requires documented PaO2 <60 mmHg on room air or SpO2 <90% requiring supplemental oxygen, with acute onset. Verify ABG or pulse ox values in clinical documentation. Common DRG upcoding target — confirm J96.11 is principal or secondary DX supported by documented respiratory management (intubation, BiPAP, supplemental O2 therapy).",
     "CMS", "ICD-10-CM 2025", CMS_ICD_URL, "2025-01-01", 0.95, "CMS ICD-10-CM tabular", "mandatory"),

    ("N18.6", "End stage renal disease",
     "icd10_cm", "high", "Diseases of the Genitourinary System", False, False,
     "both", True,
     "2024-10-01", None,
     "ESRD — highest CKD severity stage; MCC in inpatient DRG grouping. Requires documented GFR <15 or dialysis dependence. Directly affects coverage for J0885 (epoetin alfa) billing — ESRD patients use J0885 for dialysis-related anemia under separate ESRD bundle rules. Flag if N18.6 added without documented dialysis status or nephrology confirmation. Verify that epoetin alfa billing distinguishes ESRD vs non-ESRD coverage pathways.",
     "CMS", "ICD-10-CM 2025", CMS_ICD_URL, "2025-01-01", 0.95, "CMS ICD-10-CM tabular", "mandatory"),
]

NEW_DRG_CODES = [
    ("207", "Respiratory System Diagnosis with Ventilator Support 96+ Hours",
     "ms_drg", "04", "Diseases and Disorders of the Respiratory System",
     5.6423, 12.1, 14.3, False, "2025", None,
     "High-weight respiratory DRG requiring documented mechanical ventilation >=96 consecutive hours. "
     "Principal procedure: ICD-10-PCS respiratory ventilation codes (5A1935Z / 5A1945Z / 5A1955Z). "
     "Typical principal DX: J96.11 (acute respiratory failure with hypoxia), J96.01, J18.x (pneumonia), J44.1 (COPD exacerbation). "
     "Audit focus: verify ventilator start/stop timestamps in nursing and RT notes support >=96 hours — even 1 hour short drops to DRG 208 (significant weight reduction). "
     "Flag if vent hours not explicitly documented or if times appear inflated. "
     "Common RAC and MAC target due to high payment weight ($50k+ typical reimbursement).",
     "CMS", "CMS IPPS Final Rule FY2025", CMS_DRG_URL, "2025-01-01",
     0.90, "CMS MS-DRG v42 grouper tables", "mandatory"),
]


def run(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    inserted = {"cpt": 0, "hcpcs": 0, "icd": 0, "drg": 0}
    skipped = {"cpt": 0, "hcpcs": 0, "icd": 0, "drg": 0}
    try:
        # CPT codes
        for row in NEW_CPT_CODES:
            (code, desc, ctype, tier, risk, units, auth, spec,
             add_on, gp_days, eff, term, notes,
             src_auth, src_doc, src_url, reviewed,
             confidence, conf_notes, certainty) = row
            exists = conn.execute(
                "SELECT 1 FROM cpt_codes WHERE code = ?", (code,)
            ).fetchone()
            if exists:
                print(f"  SKIP CPT {code} — already exists")
                skipped["cpt"] += 1
                continue
            conn.execute(
                "INSERT INTO cpt_codes "
                "(cpt_code_id, code, description, code_type, value_tier, risk_score, "
                "typical_units_max, requires_auth, specialty_typical, is_add_on, "
                "global_period_days, effective_date, termination_date, audit_notes, "
                "source_authority, source_document, source_url, last_reviewed_at, "
                "data_confidence, data_confidence_notes, rule_certainty, "
                "created_at, updated_at) VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (str(uuid4()), code, desc, ctype, tier, risk, units, auth, spec,
                 int(add_on), gp_days, eff, term, notes,
                 src_auth, src_doc, src_url, reviewed,
                 confidence, conf_notes, certainty, NOW, NOW),
            )
            print(f"  INSERT CPT {code}")
            inserted["cpt"] += 1

        # HCPCS codes (same table as CPT)
        for row in NEW_HCPCS_CODES:
            (code, desc, ctype, tier, risk, units, auth, spec,
             add_on, gp_days, eff, term, notes,
             src_auth, src_doc, src_url, reviewed,
             confidence, conf_notes, certainty) = row
            exists = conn.execute(
                "SELECT 1 FROM cpt_codes WHERE code = ?", (code,)
            ).fetchone()
            if exists:
                print(f"  SKIP HCPCS {code} — already exists")
                skipped["hcpcs"] += 1
                continue
            conn.execute(
                "INSERT INTO cpt_codes "
                "(cpt_code_id, code, description, code_type, value_tier, risk_score, "
                "typical_units_max, requires_auth, specialty_typical, is_add_on, "
                "global_period_days, effective_date, termination_date, audit_notes, "
                "source_authority, source_document, source_url, last_reviewed_at, "
                "data_confidence, data_confidence_notes, rule_certainty, "
                "created_at, updated_at) VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (str(uuid4()), code, desc, ctype, tier, risk, units, auth, spec,
                 int(add_on), gp_days, eff, term, notes,
                 src_auth, src_doc, src_url, reviewed,
                 confidence, conf_notes, certainty, NOW, NOW),
            )
            print(f"  INSERT HCPCS {code}")
            inserted["hcpcs"] += 1

        # ICD-10 codes
        for row in NEW_ICD_CODES:
            (code, desc, ctype, tier, chapter, manif, etiol,
             setting, valid_pdx,
             eff, term, notes,
             src_auth, src_doc, src_url, reviewed,
             confidence, conf_notes, certainty) = row
            exists = conn.execute(
                "SELECT 1 FROM icd_codes WHERE code = ?", (code,)
            ).fetchone()
            if exists:
                print(f"  SKIP ICD {code} — already exists")
                skipped["icd"] += 1
                continue
            conn.execute(
                "INSERT INTO icd_codes "
                "(icd_code_id, code, description, code_type, value_tier, chapter, "
                "is_manifestation, is_etiology, typical_setting, valid_as_primary_dx, "
                "effective_date, termination_date, audit_notes, "
                "source_authority, source_document, source_url, last_reviewed_at, "
                "data_confidence, data_confidence_notes, rule_certainty, "
                "created_at, updated_at) VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (str(uuid4()), code, desc, ctype, tier, chapter,
                 int(manif), int(etiol), setting, int(valid_pdx),
                 eff, term, notes,
                 src_auth, src_doc, src_url, reviewed,
                 confidence, conf_notes, certainty, NOW, NOW),
            )
            print(f"  INSERT ICD {code}")
            inserted["icd"] += 1

        # DRG codes
        for row in NEW_DRG_CODES:
            (code, desc, dtype, mdc, mdc_desc, weight, gmlos, amlos,
             surgical, eff_fy, term_fy, criteria,
             src_auth, src_doc, src_url, reviewed,
             confidence, conf_notes, certainty) = row
            exists = conn.execute(
                "SELECT 1 FROM drg_codes WHERE code = ?", (code,)
            ).fetchone()
            if exists:
                print(f"  SKIP DRG {code} — already exists")
                skipped["drg"] += 1
                continue
            conn.execute(
                "INSERT INTO drg_codes "
                "(drg_code_id, code, description, drg_type, mdc, mdc_description, "
                "weight, geometric_mean_los, arithmetic_mean_los, is_surgical, "
                "effective_fy, termination_fy, clinical_criteria, "
                "source_authority, source_document, source_url, last_reviewed_at, "
                "data_confidence, data_confidence_notes, rule_certainty, "
                "created_at, updated_at) VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (str(uuid4()), code, desc, dtype, mdc, mdc_desc,
                 weight, gmlos, amlos, int(surgical),
                 eff_fy, term_fy, criteria,
                 src_auth, src_doc, src_url, reviewed,
                 confidence, conf_notes, certainty, NOW, NOW),
            )
            print(f"  INSERT DRG {code}")
            inserted["drg"] += 1

        conn.commit()
        print(
            f"\nDone — inserted {inserted['cpt']} CPT, {inserted['hcpcs']} HCPCS, "
            f"{inserted['icd']} ICD-10, {inserted['drg']} DRG  |  "
            f"skipped {sum(skipped.values())} already-present"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    run()
