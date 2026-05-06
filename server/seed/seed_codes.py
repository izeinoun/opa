"""Seed CPT codes, ICD codes, and CPT-ICD risk pairs — synchronous sqlite3."""
from __future__ import annotations

import os
import sqlite3
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW = "2024-01-01T08:00:00"

# (code, description, value_tier, risk_score, typical_units_max, requires_auth, specialty_typical)
CPT_CODES = [
    ("99213", "Office/outpatient visit, established patient, low complexity",     "moderate", 0.10, 1, 0, "Internal Medicine"),
    ("99214", "Office/outpatient visit, established patient, moderate complexity", "high",     0.20, 1, 0, "Internal Medicine"),
    ("99215", "Office/outpatient visit, established patient, high complexity",     "high",     0.30, 1, 0, "Internal Medicine"),
    ("99232", "Subsequent hospital care, moderate complexity",                     "high",     0.35, 1, 0, "Internal Medicine"),
    ("93000", "Electrocardiogram, routine ECG with at least 12 leads",             "moderate", 0.15, 1, 0, "Cardiology"),
    ("93306", "Echocardiography, transthoracic, complete",                         "high",     0.40, 1, 1, "Cardiology"),
    ("93458", "Left heart catheterization with coronary angiography",              "high",     0.70, 1, 1, "Cardiology"),
    ("27447", "Total knee arthroplasty",                                           "high",     0.65, 1, 1, "Orthopedic Surgery"),
    ("29881", "Arthroscopy, knee, surgical; with meniscectomy",                    "high",     0.55, 1, 1, "Orthopedic Surgery"),
    ("97110", "Therapeutic exercises, each 15 minutes",                            "moderate", 0.25, 4, 0, "Physical Therapy"),
    ("97530", "Therapeutic activities, each 15 minutes",                           "moderate", 0.30, 4, 0, "Physical Therapy"),
    ("70553", "MRI brain with and without contrast",                               "high",     0.35, 1, 1, "Radiology"),
    ("72148", "MRI lumbar spine without contrast",                                 "moderate", 0.25, 1, 0, "Radiology"),
    ("99285", "Emergency department visit, high medical decision making",          "high",     0.45, 1, 0, "Emergency Medicine"),
    ("99291", "Critical care, evaluation and management, first 30-74 minutes",     "high",     0.60, 1, 0, "Emergency Medicine"),
]

# (code, description, value_tier)
ICD_CODES = [
    ("I25.10", "Atherosclerotic heart disease of native coronary artery without angina pectoris", "high"),
    ("I21.09", "ST elevation myocardial infarction involving other coronary artery of anterior wall", "high"),
    ("M17.11", "Primary osteoarthritis, right knee",                          "moderate"),
    ("M17.12", "Primary osteoarthritis, left knee",                           "moderate"),
    ("M54.5",  "Low back pain",                                               "low"),
    ("G43.909","Migraine, unspecified, not intractable, without status migrainosus", "moderate"),
    ("G35",    "Multiple sclerosis",                                          "high"),
    ("S82.001A","Fracture of patella, unspecified, initial encounter for closed fracture", "high"),
    ("Z87.39", "Personal history of other endocrine, nutritional and metabolic diseases", "low"),
    ("E11.9",  "Type 2 diabetes mellitus without complications",              "moderate"),
    ("J18.9",  "Pneumonia, unspecified organism",                             "moderate"),
    ("I10",    "Essential (primary) hypertension",                            "low"),
    ("N18.3",  "Chronic kidney disease, stage 3 (moderate)",                  "high"),
    ("R07.9",  "Chest pain, unspecified",                                     "moderate"),
    ("Z00.00", "Encounter for general adult medical examination without abnormal findings", "low"),
]

# (cpt_code, icd_code, mismatch_risk_score, rationale)
CPT_ICD_RISKS = [
    # High-risk pairs
    ("93458", "M17.11", 0.92, "Cardiac catheterization billed for knee osteoarthritis — high mismatch"),
    ("93458", "M54.5",  0.88, "Left heart cath billed for low back pain — clinically unjustified"),
    ("27447", "I10",    0.75, "Total knee replacement billed with hypertension only — missing orthopedic DX"),
    ("99215", "Z00.00", 0.65, "High-complexity E&M billed for routine wellness exam — upcoding risk"),
    ("93306", "M17.12", 0.80, "Echocardiogram billed for knee osteoarthritis — procedure-DX mismatch"),
    ("97110", "I25.10", 0.70, "PT therapeutic exercises billed for coronary artery disease — specialty mismatch"),
    # Additional pairs
    ("99232", "Z00.00", 0.60, "Subsequent hospital care billed with routine exam DX"),
    ("93000", "M54.5",  0.55, "ECG billed for low back pain — minimal clinical relationship"),
    ("29881", "E11.9",  0.50, "Knee arthroscopy billed with diabetes only — missing orthopedic indication"),
    ("70553", "I10",    0.45, "Brain MRI billed for hypertension — clinical justification required"),
    ("72148", "I25.10", 0.50, "Lumbar spine MRI billed for coronary artery disease — mismatch"),
    ("99291", "M17.11", 0.65, "Critical care billed for knee osteoarthritis — severity mismatch"),
    ("97530", "I21.09", 0.72, "PT activities billed for acute MI — not standard of care without cardiac rehab"),
    ("99285", "Z00.00", 0.60, "ED high-complexity visit billed with routine wellness DX"),
    ("93458", "E11.9",  0.55, "Cardiac cath billed with diabetes only — missing cardiac indication"),
    ("27447", "G43.909",0.82, "Total knee arthroplasty billed for migraine — extreme DX-procedure mismatch"),
    ("99215", "M54.5",  0.35, "High-complexity E&M for low back pain — possible but frequency monitored"),
    ("93306", "J18.9",  0.40, "Echocardiography billed with pneumonia — verify cardiac indication"),
    ("99232", "Z87.39", 0.38, "Subsequent hospital care with only personal history DX — unlikely inpatient"),
    ("70553", "M54.5",  0.42, "Brain MRI billed for low back pain — body region mismatch"),
]


def run(db_path: str = DB_PATH) -> int:
    conn = sqlite3.connect(db_path)
    try:
        if conn.execute("SELECT COUNT(*) FROM cpt_codes").fetchone()[0]:
            print("  cpt_codes already seeded — skipping")
            return 0

        for code, desc, tier, risk, units_max, req_auth, specialty in CPT_CODES:
            conn.execute(
                "INSERT INTO cpt_codes "
                "(cpt_code_id, code, description, value_tier, risk_score, "
                "typical_units_max, requires_auth, specialty_typical, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (str(uuid4()), code, desc, tier, risk, units_max, req_auth, specialty, NOW, NOW),
            )

        for code, desc, tier in ICD_CODES:
            conn.execute(
                "INSERT INTO icd_codes "
                "(icd_code_id, code, description, value_tier, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (str(uuid4()), code, desc, tier, NOW, NOW),
            )

        for cpt, icd, risk, rationale in CPT_ICD_RISKS:
            conn.execute(
                "INSERT INTO cpt_icd_risks "
                "(cpt_icd_risk_id, cpt_code, icd_code, mismatch_risk_score, rationale, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (str(uuid4()), cpt, icd, risk, rationale, NOW, NOW),
            )

        conn.commit()
        print(f"  Inserted {len(CPT_CODES)} CPTs, {len(ICD_CODES)} ICDs, {len(CPT_ICD_RISKS)} risk pairs")
        return len(CPT_CODES) + len(ICD_CODES) + len(CPT_ICD_RISKS)
    finally:
        conn.close()


if __name__ == "__main__":
    run()
