"""Seed CPT, ICD-10, DRG, modifier codes and their coverage/modifier maps."""
from __future__ import annotations

import json
import os
import sqlite3
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW = "2024-01-01T08:00:00"

AMA_URL  = "https://www.ama-assn.org/practice-management/cpt"
CMS_ICD_URL = "https://www.cms.gov/medicare/coding-billing/icd-10-codes"
CMS_DRG_URL = "https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps"
CMS_NCCI_URL = "https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits"

# ── CPT codes ─────────────────────────────────────────────────────────────────
# (code, description, code_type, value_tier, risk_score, typical_units_max,
#  requires_auth, specialty_typical, is_add_on, global_period_days,
#  effective_date, termination_date, audit_notes,
#  source_authority, source_document, source_url, last_reviewed_at,
#  data_confidence, data_confidence_notes, rule_certainty)
CPT_CODES = [
    ("99213", "Office/outpatient visit, established patient, low complexity",
     "cpt", "moderate", 0.10, 1, False, "Internal Medicine", False, 0,
     "2024-01-01", None,
     "E&M level 3. Common upcoding target — verify documented complexity matches MDM or time thresholds. Flag when paired with Z00.00 (wellness) or when billed at high frequency without MDM documentation.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.95, "Pulled from AMA CPT 2025 tabular", "mandatory"),

    ("99214", "Office/outpatient visit, established patient, moderate complexity",
     "cpt", "high", 0.20, 1, False, "Internal Medicine", False, 0,
     "2024-01-01", None,
     "E&M level 4. Requires documented moderate MDM or 30-39 minutes total time. High upcoding risk when patient complexity does not support moderate MDM — verify problem complexity, data reviewed, and risk of treatment.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.95, "Pulled from AMA CPT 2025 tabular", "mandatory"),

    ("99215", "Office/outpatient visit, established patient, high complexity",
     "cpt", "high", 0.30, 1, False, "Internal Medicine", False, 0,
     "2024-01-01", None,
     "E&M level 5 — highest outpatient complexity. Requires high MDM or 40+ min total time. High upcoding risk; flag when billed for wellness visits (Z00.00) or routine chronic management without documented acuity.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.95, "Pulled from AMA CPT 2025 tabular", "mandatory"),

    ("99232", "Subsequent hospital care, moderate complexity",
     "cpt", "high", 0.35, 1, False, "Internal Medicine", False, 0,
     "2024-01-01", None,
     "Inpatient subsequent care. Verify documented daily assessment in H&P or progress note. Flag if principal DX is low-acuity or if LOS seems short relative to documented complexity.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.95, "Pulled from AMA CPT 2025 tabular", "mandatory"),

    ("93000", "Electrocardiogram, routine ECG with at least 12 leads",
     "cpt", "moderate", 0.15, 1, False, "Cardiology", False, 0,
     "2024-01-01", None,
     "ECG — generally low risk. Flag when billed repeatedly for same patient without documented cardiac indication, or when billed with non-cardiac primary diagnoses.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.95, "Pulled from AMA CPT 2025 tabular", "mandatory"),

    ("93306", "Echocardiography, transthoracic, complete",
     "cpt", "high", 0.40, 1, True, "Cardiology", False, 0,
     "2024-01-01", None,
     "Complete TTE — prior auth typically required. Often billed with 26 (professional) or TC (technical) modifier split. Flag when primary DX is non-cardiac (musculoskeletal, metabolic). Verify documented cardiac indication per LCD.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.95, "Pulled from AMA CPT 2025 tabular", "mandatory"),

    ("93458", "Left heart catheterization with coronary angiography",
     "cpt", "high", 0.70, 1, True, "Cardiology", False, 90,
     "2024-01-01", None,
     "High-value cardiac invasive procedure — 90-day global period. Requires documented cardiac indication (chest pain, abnormal stress test, ACS). High audit risk when primary DX is non-cardiac. Verify pre-procedure evaluation and catheterization report.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.95, "Pulled from AMA CPT 2025 tabular", "mandatory"),

    ("27447", "Total knee arthroplasty",
     "cpt", "high", 0.65, 1, True, "Orthopedic Surgery", False, 90,
     "2024-01-01", None,
     "Major orthopedic surgery — 90-day global period. Requires musculoskeletal DX (M17.x, M16.x). Prior auth required. Flag when DX is non-orthopedic. Verify operative note, implant documentation, and H&P. High value — check for duplicate billing or bilateral upcoding.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.95, "Pulled from AMA CPT 2025 tabular", "mandatory"),

    ("29881", "Arthroscopy, knee, surgical; with meniscectomy",
     "cpt", "high", 0.55, 1, True, "Orthopedic Surgery", False, 90,
     "2024-01-01", None,
     "Knee arthroscopy — 90-day global. Requires documented meniscal tear or internal derangement. Flag if only DX is systemic (diabetes, hypertension) without orthopedic indication. Verify operative report.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.95, "Pulled from AMA CPT 2025 tabular", "mandatory"),

    ("97110", "Therapeutic exercises, each 15 minutes",
     "cpt", "moderate", 0.25, 4, False, "Physical Therapy", False, 0,
     "2024-01-01", None,
     "PT therapeutic exercise — typically billed in units (max 4/day). Verify DX supports PT (musculoskeletal, post-surgical). Flag when primary DX is cardiac or systemic without documented functional limitation. Units > 4 per session require documentation.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.95, "Pulled from AMA CPT 2025 tabular", "mandatory"),

    ("97530", "Therapeutic activities, each 15 minutes",
     "cpt", "moderate", 0.30, 4, False, "Physical Therapy", False, 0,
     "2024-01-01", None,
     "PT therapeutic activities — functional tasks. Same unit rules as 97110. Flag when paired with acute cardiac DX (I21.x) — cardiac PT is a distinct program (93797/93798), not 97530.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.95, "Pulled from AMA CPT 2025 tabular", "mandatory"),

    ("70553", "MRI brain with and without contrast",
     "cpt", "high", 0.35, 1, True, "Radiology", False, 0,
     "2024-01-01", None,
     "Brain MRI with contrast — prior auth common. Requires neurological indication (headache, MS, tumor workup, stroke). Flag when primary DX is non-neurological (musculoskeletal, GI). Verify radiology report.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.95, "Pulled from AMA CPT 2025 tabular", "mandatory"),

    ("72148", "MRI lumbar spine without contrast",
     "cpt", "moderate", 0.25, 1, False, "Radiology", False, 0,
     "2024-01-01", None,
     "Lumbar spine MRI — high volume procedure. Requires spinal indication (radiculopathy, low back pain with red flags, post-surgical). Flag when DX is non-spinal. Some MACs require conservative treatment trial before approval.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.95, "Pulled from AMA CPT 2025 tabular", "mandatory"),

    ("99285", "Emergency department visit, high medical decision making",
     "cpt", "high", 0.45, 1, False, "Emergency Medicine", False, 0,
     "2024-01-01", None,
     "ED high-complexity visit. Highest ED E&M level — requires high MDM. Flag when paired with low-acuity DX (Z00.00, minor injury). Review physician documentation for MDM criteria: multiple chronic conditions, drug therapy requiring monitoring, or high risk of complications.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.95, "Pulled from AMA CPT 2025 tabular", "mandatory"),

    ("99291", "Critical care, evaluation and management, first 30-74 minutes",
     "cpt", "high", 0.60, 1, False, "Emergency Medicine", False, 0,
     "2024-01-01", None,
     "Critical care — highest E&M value. Requires documented critical illness (failure of vital organ system or imminent risk) and physician time spent. Flag when DX is not critical-level (osteoarthritis, routine DM). Verify time documentation and ICU/CCU setting.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.95, "Pulled from AMA CPT 2025 tabular", "mandatory"),
]

# ── ICD-10-CM codes ───────────────────────────────────────────────────────────
# (code, description, code_type, value_tier, chapter, is_manifestation, is_etiology,
#  typical_setting, valid_as_inpatient_pdx,
#  effective_date, termination_date, audit_notes,
#  source_authority, source_document, source_url, last_reviewed_at,
#  data_confidence, data_confidence_notes, rule_certainty)
ICD_CODES = [
    ("I25.10", "Atherosclerotic heart disease of native coronary artery without angina pectoris",
     "icd10_cm", "high", "Diseases of the Circulatory System", False, False,
     "both", True,
     "2024-10-01", None,
     "Stable CAD — valid cardiac indication for echo, stress test, and cath. Does not alone justify PT or musculoskeletal procedures. Chronic management condition. DRG 302/303/304 as principal inpatient DX.",
     "CMS", "ICD-10-CM 2025", CMS_ICD_URL, "2025-01-01", 0.95, "CMS ICD-10-CM tabular", "mandatory"),

    ("I21.09", "ST elevation myocardial infarction involving other coronary artery of anterior wall",
     "icd10_cm", "high", "Diseases of the Circulatory System", False, False,
     "inpatient", True,
     "2024-10-01", None,
     "Acute STEMI — highest cardiac acuity. Justifies emergent cath (93458), critical care (99291), and inpatient admission. Does not justify PT, ortho, or outpatient procedures billed concurrently.",
     "CMS", "ICD-10-CM 2025", CMS_ICD_URL, "2025-01-01", 0.95, "CMS ICD-10-CM tabular", "mandatory"),

    ("M17.11", "Primary osteoarthritis, right knee",
     "icd10_cm", "moderate", "Diseases of the Musculoskeletal System", False, False,
     "outpatient", True,
     "2024-10-01", None,
     "Right knee OA — primary indication for 27447 (TKA) and 29881 (arthroscopy). Valid for PT (97110, 97530). Does not justify cardiac or neurological procedures.",
     "CMS", "ICD-10-CM 2025", CMS_ICD_URL, "2025-01-01", 0.95, "CMS ICD-10-CM tabular", "mandatory"),

    ("M17.12", "Primary osteoarthritis, left knee",
     "icd10_cm", "moderate", "Diseases of the Musculoskeletal System", False, False,
     "outpatient", True,
     "2024-10-01", None,
     "Left knee OA — same applicability as M17.11 for right knee. Flag when paired with cardiac or non-orthopedic high-value procedures.",
     "CMS", "ICD-10-CM 2025", CMS_ICD_URL, "2025-01-01", 0.95, "CMS ICD-10-CM tabular", "mandatory"),

    ("M54.5", "Low back pain",
     "icd10_cm", "low", "Diseases of the Musculoskeletal System", False, False,
     "outpatient", True,
     "2024-10-01", None,
     "Non-specific low back pain — valid for 72148 (lumbar MRI) and PT. Low acuity. Flag when paired with high-complexity E&M or invasive cardiac/neuro procedures without additional documented indications.",
     "CMS", "ICD-10-CM 2025", CMS_ICD_URL, "2025-01-01", 0.95, "CMS ICD-10-CM tabular", "mandatory"),

    ("G43.909", "Migraine, unspecified, not intractable, without status migrainosus",
     "icd10_cm", "moderate", "Diseases of the Nervous System", False, False,
     "outpatient", True,
     "2024-10-01", None,
     "Migraine — valid for 70553 (brain MRI) to rule out secondary causes. Does not justify musculoskeletal surgery, cardiac procedures, or PT for functional limitation.",
     "CMS", "ICD-10-CM 2025", CMS_ICD_URL, "2025-01-01", 0.95, "CMS ICD-10-CM tabular", "mandatory"),

    ("G35", "Multiple sclerosis",
     "icd10_cm", "high", "Diseases of the Nervous System", False, False,
     "both", True,
     "2024-10-01", None,
     "MS — primary indication for brain and spinal MRI. May justify PT for functional deficits. High-value chronic condition requiring longitudinal monitoring.",
     "CMS", "ICD-10-CM 2025", CMS_ICD_URL, "2025-01-01", 0.95, "CMS ICD-10-CM tabular", "mandatory"),

    ("S82.001A", "Fracture of patella, unspecified, initial encounter for closed fracture",
     "icd10_cm", "high", "Injury, Poisoning and Certain Other Consequences", False, False,
     "both", True,
     "2024-10-01", None,
     "Acute patellar fracture — initial encounter ('A'). May justify ortho visit, imaging, PT. Verify 7th character is correct for encounter type.",
     "CMS", "ICD-10-CM 2025", CMS_ICD_URL, "2025-01-01", 0.95, "CMS ICD-10-CM tabular", "mandatory"),

    ("Z87.39", "Personal history of other endocrine, nutritional and metabolic diseases",
     "icd10_cm", "low", "Factors Influencing Health Status", False, False,
     "both", False,
     "2024-10-01", None,
     "History code — MCE unacceptable as inpatient principal DX. Should only appear as secondary DX. Flag when listed as sole justification for a high-complexity visit or procedure.",
     "CMS", "ICD-10-CM 2025", CMS_ICD_URL, "2025-01-01", 0.95, "CMS ICD-10-CM tabular", "mandatory"),

    ("E11.9", "Type 2 diabetes mellitus without complications",
     "icd10_cm", "moderate", "Endocrine, Nutritional and Metabolic Diseases", False, False,
     "both", True,
     "2024-10-01", None,
     "Uncomplicated T2DM — secondary DX in inpatient; affects DRG CC/MCC severity. Does not alone justify invasive procedures. Verify additional DX supports any high-value procedure billed.",
     "CMS", "ICD-10-CM 2025", CMS_ICD_URL, "2025-01-01", 0.95, "CMS ICD-10-CM tabular", "mandatory"),

    ("J18.9", "Pneumonia, unspecified organism",
     "icd10_cm", "moderate", "Diseases of the Respiratory System", False, False,
     "inpatient", True,
     "2024-10-01", None,
     "DRG 193/194/195. Requires clinical physician diagnosis — not solely imaging infiltrate. Specify organism when identified. Common MCC pairing: sepsis, respiratory failure.",
     "CMS", "ICD-10-CM 2025", CMS_ICD_URL, "2025-01-01", 0.95, "CMS ICD-10-CM tabular", "mandatory"),

    ("I10", "Essential (primary) hypertension",
     "icd10_cm", "low", "Diseases of the Circulatory System", False, False,
     "both", True,
     "2024-10-01", None,
     "Hypertension alone is low acuity. Secondary CC in inpatient. Does not justify orthopedic surgery or invasive cardiac procedures without additional indications. Very commonly present as secondary DX.",
     "CMS", "ICD-10-CM 2025", CMS_ICD_URL, "2025-01-01", 0.95, "CMS ICD-10-CM tabular", "mandatory"),

    ("N18.3", "Chronic kidney disease, stage 3 (moderate)",
     "icd10_cm", "high", "Diseases of the Genitourinary System", False, False,
     "both", True,
     "2024-10-01", None,
     "CKD stage 3 — significant MCC/CC; elevates DRG weight. Verify lab values support CKD3 (GFR 30-59). Flag if used to justify DRG upgrade without supporting nephrology documentation.",
     "CMS", "ICD-10-CM 2025", CMS_ICD_URL, "2025-01-01", 0.95, "CMS ICD-10-CM tabular", "mandatory"),

    ("R07.9", "Chest pain, unspecified",
     "icd10_cm", "moderate", "Symptoms, Signs and Abnormal Clinical and Laboratory Findings", False, False,
     "both", True,
     "2024-10-01", None,
     "Symptom code — valid as first-listed DX for ED visits and cardiac workup. Should be replaced with definitive DX once established. Flag if used repeatedly without diagnostic progression.",
     "CMS", "ICD-10-CM 2025", CMS_ICD_URL, "2025-01-01", 0.95, "CMS ICD-10-CM tabular", "mandatory"),

    ("Z00.00", "Encounter for general adult medical examination without abnormal findings",
     "icd10_cm", "low", "Factors Influencing Health Status", False, False,
     "outpatient", False,
     "2024-10-01", None,
     "Wellness visit — MCE unacceptable as inpatient principal DX. Cannot support high-complexity E&M (99215) or procedures requiring medical necessity. Flag when paired with therapeutic procedure codes.",
     "CMS", "ICD-10-CM 2025", CMS_ICD_URL, "2025-01-01", 0.95, "CMS ICD-10-CM tabular", "mandatory"),
]

# ── DRG codes ─────────────────────────────────────────────────────────────────
# (code, description, drg_type, mdc, mdc_description,
#  weight, geometric_mean_los, arithmetic_mean_los, is_surgical,
#  effective_fy, termination_fy, clinical_criteria,
#  source_authority, source_document, source_url, last_reviewed_at,
#  data_confidence, data_confidence_notes, rule_certainty)
DRG_CODES = [
    ("470", "Major Joint Replacement or Reattachment of Lower Extremity without MCC",
     "ms_drg", "08", "Diseases and Disorders of the Musculoskeletal System and Connective Tissue",
     2.0454, 2.4, 2.8, True, "2025", None,
     "Typical principal DX: M17.11/M17.12 (knee OA), M16.11/M16.12 (hip OA). Principal procedure: total knee arthroplasty (0SRC/0SRD ICD-10-PCS) or total hip arthroplasty (0SR9/0SRB). "
     "No MCC present — if MCC documented (CKD3+, CHF, COPD) claim should group to DRG 469. "
     "Expected LOS 2-4 days. Flag if LOS >7 days without documented complication. "
     "Implant coding required. Verify operative note matches DRG grouper principal procedure.",
     "CMS", "CMS IPPS Final Rule FY2025", CMS_DRG_URL, "2025-01-01",
     0.90, "CMS MS-DRG v42 grouper tables", "mandatory"),

    ("469", "Major Joint Replacement or Reattachment of Lower Extremity with MCC",
     "ms_drg", "08", "Diseases and Disorders of the Musculoskeletal System and Connective Tissue",
     3.2371, 3.8, 4.6, True, "2025", None,
     "Same procedure as DRG 470 but with documented MCC (e.g. N18.3 CKD3, I50.x CHF, J44.x COPD). "
     "Higher payment weight reflects increased complexity. Verify MCC is genuine, documented, and treated during this encounter — not merely a historical condition. "
     "Common audit target: DRG 469 vs 470 upcoding via inflated CC/MCC coding.",
     "CMS", "CMS IPPS Final Rule FY2025", CMS_DRG_URL, "2025-01-01",
     0.90, "CMS MS-DRG v42 grouper tables", "mandatory"),

    ("280", "Acute Myocardial Infarction, Discharged Alive with MCC",
     "ms_drg", "05", "Diseases and Disorders of the Circulatory System",
     2.2849, 4.2, 5.1, False, "2025", None,
     "Principal DX: I21.x (STEMI) or I22.x (subsequent MI). MCC must be documented and treated. "
     "Typical procedures: 93458 (diagnostic cath), percutaneous intervention (0270-027F ICD-10-PCS). "
     "Flag if patient discharged <2 days — verify medical necessity for admission vs observation. "
     "Cardiac enzyme documentation (troponin) required to support AMI DX.",
     "CMS", "CMS IPPS Final Rule FY2025", CMS_DRG_URL, "2025-01-01",
     0.90, "CMS MS-DRG v42 grouper tables", "mandatory"),

    ("247", "Percutaneous Cardiovascular Procedure with Drug-Eluting Stent with MCC or 4+ Arteries/Stents",
     "ms_drg", "05", "Diseases and Disorders of the Circulatory System",
     3.2087, 3.1, 4.0, True, "2025", None,
     "High-value interventional cardiology DRG. Requires PCI procedure with drug-eluting stent (ICD-10-PCS 027x4ZZ or similar). "
     "MCC or ≥4 vessels/stents triggers this DRG vs 248/249. "
     "Audit focus: confirm stent count matches operative/cath lab report. Drug-eluting vs bare-metal stent distinction affects DRG. "
     "Principal DX typically I25.10 (stable CAD), I21.x (AMI), or I20.0 (unstable angina).",
     "CMS", "CMS IPPS Final Rule FY2025", CMS_DRG_URL, "2025-01-01",
     0.90, "CMS MS-DRG v42 grouper tables", "mandatory"),

    ("291", "Heart Failure and Shock with MCC",
     "ms_drg", "05", "Diseases and Disorders of the Circulatory System",
     1.7434, 4.6, 5.8, False, "2025", None,
     "Principal DX: I50.x (heart failure). MCC required — typically respiratory failure, renal failure, or sepsis. "
     "Systolic vs diastolic HF distinction affects specificity. Flag if HF DX not supported by BNP/echo documentation. "
     "Audit: confirm MCC is treated, not incidental. Common DRG for RAC audit.",
     "CMS", "CMS IPPS Final Rule FY2025", CMS_DRG_URL, "2025-01-01",
     0.90, "CMS MS-DRG v42 grouper tables", "mandatory"),

    ("392", "Esophagitis, Gastroenteritis and Miscellaneous Digestive Disorders without MCC",
     "ms_drg", "06", "Diseases and Disorders of the Digestive System",
     0.7234, 2.3, 2.9, False, "2025", None,
     "Low-weight medical DRG. Principal DX: gastroenteritis (K52.x), esophagitis (K20.x), or other GI disorders. "
     "No MCC present. Short expected LOS. Flag if LOS >4 days without documented complication justifying extended stay. "
     "Common site-of-service concern: verify inpatient vs observation status for short-stay GI admissions.",
     "CMS", "CMS IPPS Final Rule FY2025", CMS_DRG_URL, "2025-01-01",
     0.90, "CMS MS-DRG v42 grouper tables", "mandatory"),

    ("192", "Chronic Obstructive Pulmonary Disease with MCC",
     "ms_drg", "04", "Diseases and Disorders of the Respiratory System",
     1.4823, 3.8, 4.7, False, "2025", None,
     "Principal DX: J44.x (COPD with acute exacerbation or lower respiratory infection). MCC required. "
     "Verify spirometry or documented exacerbation with bronchodilator treatment. "
     "Flag if COPD DX added to non-respiratory admission solely to increase DRG weight (upcoding pattern).",
     "CMS", "CMS IPPS Final Rule FY2025", CMS_DRG_URL, "2025-01-01",
     0.90, "CMS MS-DRG v42 grouper tables", "mandatory"),
]

# ── Modifier codes ────────────────────────────────────────────────────────────
# (code, description, modifier_type, applies_to,
#  payment_impact, payment_factor,
#  ncci_override, requires_documentation, audit_risk_score,
#  valid_cpt_prefixes, mutually_exclusive_with, audit_notes,
#  source_authority, source_document, source_url, last_reviewed_at,
#  data_confidence, data_confidence_notes, rule_certainty)
MODIFIER_CODES = [
    ("25", "Significant, separately identifiable evaluation and management service by the same physician on the same day of the procedure",
     "informational", "cpt", "none", None, False, True, 0.65,
     json.dumps(["992", "993", "994", "995", "996", "997", "998", "999"]),
     json.dumps(["57"]),
     "High audit risk. Requires separate, documented E&M distinct from pre/post-procedure work. Flag when 25 is applied routinely to all E&M+procedure visits without individualized documentation. CMS and RAC frequently audit 25 overuse.",
     "AMA", "CPT 2025 Appendix A", AMA_URL, "2025-01-01", 0.95, "AMA CPT 2025", "mandatory"),

    ("26", "Professional component",
     "pricing", "both", "reduce", None, False, False, 0.15,
     json.dumps(["700", "701", "702", "703", "704", "705", "706", "707", "708", "709",
                 "710", "711", "712", "713", "714", "715", "716", "717", "718", "719",
                 "720", "721", "722", "723", "724", "725", "726", "727", "728", "729",
                 "730", "731", "732", "733", "734", "735", "736", "737", "738", "739",
                 "740", "741", "742", "743", "744", "745", "746", "747", "748", "749",
                 "930", "931", "932", "933", "934", "935", "936", "937", "938", "939"]),
     json.dumps(["TC"]),
     "Professional component — used when physician interprets but does not own equipment. Must not be billed with TC on same claim for same service. Verify split-billing arrangement is in place.",
     "AMA", "CPT 2025 Appendix A", AMA_URL, "2025-01-01", 0.95, "AMA CPT 2025", "mandatory"),

    ("TC", "Technical component",
     "pricing", "both", "reduce", None, False, False, 0.10,
     json.dumps(["700", "701", "702", "703", "930", "931", "932", "933", "934", "935"]),
     json.dumps(["26"]),
     "Technical component — facility/equipment cost. Mutually exclusive with 26 on same claim line. Verify facility bills TC and physician bills 26 separately.",
     "CMS", "CMS Physician Fee Schedule", "https://www.cms.gov/medicare/payment/fee-schedules/physician", "2025-01-01",
     0.95, "CMS PFS split-billing rules", "mandatory"),

    ("50", "Bilateral procedure",
     "payment", "cpt", "increase", 1.50, False, True, 0.30,
     json.dumps(["270", "271", "272", "273", "274", "275", "276", "277", "278", "279",
                 "280", "281", "282", "283", "284", "285", "286", "287", "288", "289",
                 "290", "291", "292", "293", "294", "295", "296", "297", "298", "299"]),
     json.dumps(["51", "LT", "RT"]),
     "Bilateral procedure — typically 150% of unilateral fee. Requires documented bilateral performance. Flag when billed for procedures rarely performed bilaterally (e.g. total knee on both sides in same session without documented necessity).",
     "AMA", "CPT 2025 Appendix A", AMA_URL, "2025-01-01", 0.95, "AMA CPT 2025", "mandatory"),

    ("51", "Multiple procedures",
     "payment", "cpt", "reduce", 0.50, False, False, 0.35,
     json.dumps(["100", "101", "102", "103", "104", "200", "201", "202", "203", "204",
                 "270", "271", "272", "273", "274", "275", "276", "277", "278", "279"]),
     json.dumps(["50"]),
     "Multiple procedures — secondary procedures reimbursed at 50%. Verify each billed procedure is distinct and not bundled. Flag if 51 is applied to procedures that should be unbundled (NCCI concern).",
     "AMA", "CPT 2025 Appendix A", AMA_URL, "2025-01-01", 0.95, "AMA CPT 2025", "mandatory"),

    ("52", "Reduced services",
     "payment", "both", "reduce", None, False, True, 0.15,
     None, json.dumps(["53"]),
     "Procedure was reduced or less than typically described. Requires documentation explaining why full service was not performed. Lower audit risk — unusual to overbill with 52.",
     "AMA", "CPT 2025 Appendix A", AMA_URL, "2025-01-01", 0.95, "AMA CPT 2025", "mandatory"),

    ("53", "Discontinued procedure",
     "informational", "cpt", "none", None, False, True, 0.20,
     None, json.dumps(["52"]),
     "Procedure started but discontinued due to patient risk. Requires documentation of reason. Flag if 53 is billed repeatedly for same procedure on same patient — pattern may indicate poor patient selection or billing manipulation.",
     "AMA", "CPT 2025 Appendix A", AMA_URL, "2025-01-01", 0.95, "AMA CPT 2025", "mandatory"),

    ("57", "Decision for surgery",
     "informational", "cpt", "none", None, False, True, 0.40,
     json.dumps(["992", "993", "994", "995", "996", "997", "998", "999"]),
     json.dumps(["25"]),
     "E&M the day before or day of major surgery where decision for surgery was made. Prevents global period bundling. Requires documented surgical decision in note. Flag when 57 is applied routinely without individualized documentation.",
     "AMA", "CPT 2025 Appendix A", AMA_URL, "2025-01-01", 0.95, "AMA CPT 2025", "mandatory"),

    ("59", "Distinct procedural service",
     "informational", "both", "bypass_edit", None, True, True, 0.75,
     None, json.dumps(["XE", "XS", "XP", "XU"]),
     "NCCI column I/II override — highest audit risk modifier. Indicates procedures are distinct and not bundled. CMS and RAC flag systematic 59 use. Requires documentation of distinct anatomic site, encounter, or indication. "
     "Preferred over XE/XS/XP/XU only when no X-modifier is more specific. OIG Work Plan annually includes 59 modifier overuse.",
     "CMS", "NCCI Policy Manual 2025", CMS_NCCI_URL, "2025-01-01",
     0.95, "CMS NCCI Policy Manual Chapter 1", "mandatory"),

    ("76", "Repeat procedure or service by same physician or other qualified health care professional",
     "informational", "both", "none", None, False, True, 0.40,
     None, None,
     "Repeat procedure — same physician, same day or subsequent day. Requires documentation explaining medical necessity for repeat. Flag when 76 appears frequently for same CPT on same patient — pattern review warranted.",
     "AMA", "CPT 2025 Appendix A", AMA_URL, "2025-01-01", 0.95, "AMA CPT 2025", "mandatory"),

    ("77", "Repeat procedure by another physician or other qualified health care professional",
     "informational", "both", "none", None, False, True, 0.35,
     None, None,
     "Repeat procedure by different physician. Less common than 76. Verify clinical necessity and that the repeat was truly by a different provider.",
     "AMA", "CPT 2025 Appendix A", AMA_URL, "2025-01-01", 0.95, "AMA CPT 2025", "mandatory"),

    ("22", "Increased procedural services",
     "payment", "cpt", "increase", None, False, True, 0.45,
     None, None,
     "Procedure required substantially greater effort than typical. Requires documentation of why service was more complex (e.g. severe obesity, adhesions, unusual anatomy). Flag when 22 is billed without supporting operative note language.",
     "AMA", "CPT 2025 Appendix A", AMA_URL, "2025-01-01", 0.95, "AMA CPT 2025", "mandatory"),

    ("24", "Unrelated evaluation and management service by the same physician or other qualified health care professional during a postoperative period",
     "informational", "cpt", "none", None, False, True, 0.40,
     json.dumps(["992", "993", "994", "995", "996", "997", "998", "999"]),
     None,
     "E&M during global period for unrelated condition. Requires documentation that E&M is truly unrelated to the surgical procedure. Flag when 24 is applied for conditions plausibly related to the surgery.",
     "AMA", "CPT 2025 Appendix A", AMA_URL, "2025-01-01", 0.95, "AMA CPT 2025", "mandatory"),

    ("80", "Assistant surgeon",
     "payment", "cpt", "reduce", 0.16, False, False, 0.35,
     None, json.dumps(["81", "82", "AS"]),
     "Assistant surgeon — 16% of primary surgeon fee. Some CPT codes do not allow assistant surgeon billing per CMS (indicator 0 in PFS). Verify CPT allows assistant surgeon before approving claim.",
     "CMS", "CMS Physician Fee Schedule", "https://www.cms.gov/medicare/payment/fee-schedules/physician", "2025-01-01",
     0.90, "CMS PFS assistant surgeon indicators", "mandatory"),

    ("GT", "Via interactive audio and video telecommunications systems",
     "service", "both", "none", None, False, False, 0.20,
     None, None,
     "Telehealth modifier. Required for CMS telehealth claims to indicate synchronous A/V technology. Verify service is on approved telehealth services list. Pandemic-era waivers extended many telehealth approvals — verify current coverage.",
     "CMS", "CMS Telehealth Services List 2025", "https://www.cms.gov/medicare/coverage/telehealth", "2025-01-01",
     0.90, "CMS MLN telehealth guidance", "mandatory"),

    ("XE", "Separate encounter",
     "informational", "both", "bypass_edit", None, True, True, 0.60,
     None, json.dumps(["59"]),
     "NCCI X-modifier subset — distinct encounter. More specific than 59; preferred when services were at separate encounters. Same high audit risk as 59. Use instead of 59 when applicable.",
     "CMS", "NCCI Policy Manual 2025", CMS_NCCI_URL, "2025-01-01",
     0.95, "CMS NCCI Policy Manual", "mandatory"),

    ("XS", "Separate structure",
     "informational", "both", "bypass_edit", None, True, True, 0.60,
     None, json.dumps(["59"]),
     "NCCI X-modifier subset — separate anatomic structure. Use when procedures were on different anatomic structures. More specific than 59.",
     "CMS", "NCCI Policy Manual 2025", CMS_NCCI_URL, "2025-01-01",
     0.95, "CMS NCCI Policy Manual", "mandatory"),

    ("XP", "Separate practitioner",
     "informational", "both", "bypass_edit", None, True, True, 0.55,
     None, json.dumps(["59"]),
     "NCCI X-modifier subset — different practitioner performed the service. Preferred over 59 when applicable.",
     "CMS", "NCCI Policy Manual 2025", CMS_NCCI_URL, "2025-01-01",
     0.95, "CMS NCCI Policy Manual", "mandatory"),

    ("XU", "Unusual non-overlapping service",
     "informational", "both", "bypass_edit", None, True, True, 0.65,
     None, json.dumps(["59"]),
     "NCCI X-modifier subset — service does not overlap usual components. Use when the service is genuinely non-overlapping with the primary procedure. Higher audit scrutiny than XE/XS/XP.",
     "CMS", "NCCI Policy Manual 2025", CMS_NCCI_URL, "2025-01-01",
     0.95, "CMS NCCI Policy Manual", "mandatory"),
]

# ── CPT → Modifier valid pairs ────────────────────────────────────────────────
# (cpt_code, modifier_code, payment_factor, ncci_override, notes,
#  source_authority, source_document, source_url, last_reviewed_at,
#  data_confidence, data_confidence_notes, rule_certainty)
CPT_MODIFIER_MAP = [
    # E&M codes + modifier 25
    ("99213", "25", None, False, "E&M with minor procedure on same day. Separate E&M documentation required.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.90, "AMA CPT 2025", "mandatory"),
    ("99214", "25", None, False, "E&M with minor procedure on same day. Separate E&M documentation required.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.90, "AMA CPT 2025", "mandatory"),
    ("99215", "25", None, False, "E&M with minor procedure on same day. Separate E&M documentation required.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.90, "AMA CPT 2025", "mandatory"),
    ("99232", "25", None, False, "Inpatient E&M with procedure. Document separate clinical decision-making.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.90, "AMA CPT 2025", "mandatory"),
    ("99285", "25", None, False, "ED E&M with procedure. Common in ED — verify documentation.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.90, "AMA CPT 2025", "mandatory"),
    # Modifier 57 — decision for major surgery
    ("99213", "57", None, False, "Decision for major surgery. Bypasses global period bundling.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.90, "AMA CPT 2025", "mandatory"),
    ("99214", "57", None, False, "Decision for major surgery. Bypasses global period bundling.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.90, "AMA CPT 2025", "mandatory"),
    ("99215", "57", None, False, "Decision for major surgery. Bypasses global period bundling.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.90, "AMA CPT 2025", "mandatory"),
    # Cardiology — professional/technical split
    ("93306", "26", None, False, "Professional component — physician reads/interprets echo only.",
     "CMS", "CMS PFS", "https://www.cms.gov/medicare/payment/fee-schedules/physician", "2025-01-01",
     0.90, "CMS PFS split billing rules", "mandatory"),
    ("93306", "TC", None, False, "Technical component — facility owns equipment.",
     "CMS", "CMS PFS", "https://www.cms.gov/medicare/payment/fee-schedules/physician", "2025-01-01",
     0.90, "CMS PFS split billing rules", "mandatory"),
    ("93000", "26", None, False, "ECG professional read-only.",
     "CMS", "CMS PFS", "https://www.cms.gov/medicare/payment/fee-schedules/physician", "2025-01-01",
     0.90, "CMS PFS split billing rules", "mandatory"),
    ("93000", "TC", None, False, "ECG technical component.",
     "CMS", "CMS PFS", "https://www.cms.gov/medicare/payment/fee-schedules/physician", "2025-01-01",
     0.90, "CMS PFS split billing rules", "mandatory"),
    # Radiology — professional/technical split
    ("70553", "26", None, False, "MRI professional read-only — radiologist interpretation.",
     "CMS", "CMS PFS", "https://www.cms.gov/medicare/payment/fee-schedules/physician", "2025-01-01",
     0.90, "CMS PFS split billing rules", "mandatory"),
    ("70553", "TC", None, False, "MRI technical component — facility/equipment.",
     "CMS", "CMS PFS", "https://www.cms.gov/medicare/payment/fee-schedules/physician", "2025-01-01",
     0.90, "CMS PFS split billing rules", "mandatory"),
    ("72148", "26", None, False, "Lumbar MRI professional read.",
     "CMS", "CMS PFS", "https://www.cms.gov/medicare/payment/fee-schedules/physician", "2025-01-01",
     0.90, "CMS PFS split billing rules", "mandatory"),
    ("72148", "TC", None, False, "Lumbar MRI technical component.",
     "CMS", "CMS PFS", "https://www.cms.gov/medicare/payment/fee-schedules/physician", "2025-01-01",
     0.90, "CMS PFS split billing rules", "mandatory"),
    # Surgical modifiers
    ("27447", "50", 1.50, False, "Bilateral total knee replacement — same session. Unusual; document necessity.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.85, "AMA CPT 2025", "mandatory"),
    ("27447", "22", None, False, "Increased complexity — severe obesity, prior surgery, or complex anatomy. Document in op note.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.90, "AMA CPT 2025", "mandatory"),
    ("27447", "80", 0.16, False, "Assistant surgeon for TKA. Verify CPT allows assistant surgeon per CMS PFS indicator.",
     "CMS", "CMS PFS", "https://www.cms.gov/medicare/payment/fee-schedules/physician", "2025-01-01",
     0.90, "CMS PFS assistant surgeon indicators", "mandatory"),
    ("29881", "51", 0.50, False, "Multiple procedures — arthroscopy with additional same-session procedure.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.90, "AMA CPT 2025", "mandatory"),
    ("29881", "22", None, False, "Increased complexity arthroscopy.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.90, "AMA CPT 2025", "mandatory"),
    # PT modifiers
    ("97110", "76", None, False, "Repeat PT session same day same therapist.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.90, "AMA CPT 2025", "mandatory"),
    ("97110", "77", None, False, "Repeat PT session by different therapist.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.90, "AMA CPT 2025", "mandatory"),
    ("97530", "76", None, False, "Repeat therapeutic activity same therapist.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.90, "AMA CPT 2025", "mandatory"),
    ("97530", "77", None, False, "Repeat therapeutic activity different therapist.",
     "AMA", "CPT 2025", AMA_URL, "2025-01-01", 0.90, "AMA CPT 2025", "mandatory"),
    # Telehealth
    ("99213", "GT", None, False, "Telehealth E&M — synchronous A/V required.",
     "CMS", "CMS Telehealth Services 2025", "https://www.cms.gov/medicare/coverage/telehealth", "2025-01-01",
     0.90, "CMS telehealth guidance", "mandatory"),
    ("99214", "GT", None, False, "Telehealth E&M.",
     "CMS", "CMS Telehealth Services 2025", "https://www.cms.gov/medicare/coverage/telehealth", "2025-01-01",
     0.90, "CMS telehealth guidance", "mandatory"),
    ("99215", "GT", None, False, "Telehealth E&M.",
     "CMS", "CMS Telehealth Services 2025", "https://www.cms.gov/medicare/coverage/telehealth", "2025-01-01",
     0.90, "CMS telehealth guidance", "mandatory"),
    # NCCI override pairs
    ("93306", "59", None, True, "Distinct service override — use only when echocardiography is performed as a separate, distinct service on the same day as another cardiac procedure.",
     "CMS", "NCCI Policy Manual 2025", CMS_NCCI_URL, "2025-01-01",
     0.90, "CMS NCCI edits", "mandatory"),
    ("93000", "59", None, True, "ECG billed as distinct service on same day as cardiac procedure.",
     "CMS", "NCCI Policy Manual 2025", CMS_NCCI_URL, "2025-01-01",
     0.90, "CMS NCCI edits", "mandatory"),
]

# ── CPT → ICD-10 coverage ─────────────────────────────────────────────────────
# (cpt_code, icd_code, coverage_type, rationale,
#  source_authority, source_document, source_url, last_reviewed_at,
#  data_confidence, data_confidence_notes, rule_certainty)
CPT_DX_COVERAGE = [
    # ── 27447 (Total Knee Arthroplasty) ──────────────────────────────────
    ("27447", "M17.11", "required",
     "Primary osteoarthritis of the right knee is the principal indication for total knee arthroplasty. Conservative treatment failure must be documented.",
     "CMS", "LCD L34041 — Total Knee Arthroplasty", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.90, "CMS MAC LCD for TKA", "mandatory"),
    ("27447", "M17.12", "required",
     "Primary osteoarthritis of the left knee. Same clinical justification as M17.11 for left-side procedure.",
     "CMS", "LCD L34041 — Total Knee Arthroplasty", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.90, "CMS MAC LCD for TKA", "mandatory"),
    ("27447", "S82.001A", "supporting",
     "Patellar fracture may necessitate knee arthroplasty in complex cases. Supporting indication only — verify operative documentation.",
     "CMS", "LCD L34041 — Total Knee Arthroplasty", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.75, "Clinical guidelines, not primary LCD indication", "guideline"),
    ("27447", "I10", "excluded",
     "Hypertension alone does not justify total knee arthroplasty. Flag if I10 is the only or primary diagnosis — missing orthopedic indication.",
     "CMS", "LCD L34041 — Total Knee Arthroplasty", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.80, "Derived from LCD medical necessity criteria", "guideline"),
    ("27447", "G43.909", "excluded",
     "Migraine has no clinical relationship to total knee arthroplasty. Extreme DX-procedure mismatch — likely coding error or fraud.",
     "CMS", "LCD L34041 — Total Knee Arthroplasty", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.95, "Clinical consensus — no plausible linkage", "mandatory"),
    ("27447", "E11.9", "excluded",
     "Uncomplicated type 2 diabetes alone does not justify knee arthroplasty. Requires concurrent orthopedic DX.",
     "CMS", "LCD L34041 — Total Knee Arthroplasty", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.80, "Derived from LCD medical necessity criteria", "guideline"),

    # ── 93458 (Left Heart Catheterization) ───────────────────────────────
    ("93458", "I25.10", "required",
     "Stable CAD is a primary indication for diagnostic cardiac catheterization. Document symptoms, prior non-invasive testing, and clinical decision-making.",
     "CMS", "LCD L33996 — Cardiac Catheterization", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.90, "CMS MAC LCD for cardiac cath", "mandatory"),
    ("93458", "I21.09", "required",
     "Acute STEMI is an emergent indication for cardiac catheterization and PCI. Cath report and clinical note required.",
     "CMS", "LCD L33996 — Cardiac Catheterization", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.95, "CMS MAC LCD for cardiac cath", "mandatory"),
    ("93458", "R07.9", "supporting",
     "Chest pain is a supporting indication for diagnostic cath when other non-invasive workup is positive or inconclusive.",
     "CMS", "LCD L33996 — Cardiac Catheterization", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.80, "CMS MAC LCD supporting criteria", "guideline"),
    ("93458", "M17.11", "excluded",
     "Knee osteoarthritis has no clinical relationship to cardiac catheterization. Cath requires a documented cardiac indication.",
     "CMS", "LCD L33996 — Cardiac Catheterization", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.95, "Clinical consensus", "mandatory"),
    ("93458", "M54.5", "excluded",
     "Low back pain does not justify left heart catheterization. Clinically unjustified — flag as probable DX-procedure mismatch.",
     "CMS", "LCD L33996 — Cardiac Catheterization", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.92, "Clinical consensus", "mandatory"),
    ("93458", "M17.12", "excluded",
     "Left knee osteoarthritis does not justify cardiac catheterization.",
     "CMS", "LCD L33996 — Cardiac Catheterization", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.92, "Clinical consensus", "mandatory"),
    ("93458", "E11.9", "excluded",
     "Uncomplicated T2DM alone does not justify cardiac catheterization. Requires documented cardiac indication (symptoms, abnormal testing).",
     "CMS", "LCD L33996 — Cardiac Catheterization", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.80, "Derived from LCD criteria", "guideline"),

    # ── 93306 (Echocardiography) ──────────────────────────────────────────
    ("93306", "I25.10", "required",
     "CAD is a primary indication for echocardiography to assess systolic function, wall motion, and valvular integrity.",
     "CMS", "LCD L33997 — Echocardiography", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.90, "CMS MAC LCD for echo", "mandatory"),
    ("93306", "I21.09", "required",
     "Acute MI — echocardiography assesses wall motion abnormality and ejection fraction. Standard of care.",
     "CMS", "LCD L33997 — Echocardiography", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.95, "CMS MAC LCD for echo", "mandatory"),
    ("93306", "R07.9", "supporting",
     "Chest pain — echo used to evaluate cardiac function when cardiac etiology suspected.",
     "CMS", "LCD L33997 — Echocardiography", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.80, "CMS MAC LCD supporting criteria", "guideline"),
    ("93306", "M17.12", "excluded",
     "Knee OA has no clinical relationship to echocardiography. Cardiac indication required.",
     "CMS", "LCD L33997 — Echocardiography", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.90, "Clinical consensus", "mandatory"),
    ("93306", "J18.9", "excluded",
     "Pneumonia alone does not justify echocardiography unless cardiac complication (e.g. pericarditis, CHF) is documented.",
     "CMS", "LCD L33997 — Echocardiography", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.65, "Guideline-based — exceptions exist", "guideline"),

    # ── 70553 (Brain MRI) ─────────────────────────────────────────────────
    ("70553", "G35", "required",
     "MS requires brain and spinal cord MRI for diagnosis and monitoring per McDonald criteria.",
     "CMS", "LCD L35031 — MRI Brain", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.95, "CMS MAC LCD for brain MRI", "mandatory"),
    ("70553", "G43.909", "supporting",
     "Migraine — brain MRI appropriate to exclude secondary causes (tumor, AVM, vascular anomaly) in new-onset or atypical migraine.",
     "CMS", "LCD L35031 — MRI Brain", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.85, "CMS MAC LCD supporting criteria", "guideline"),
    ("70553", "M54.5", "excluded",
     "Low back pain does not justify brain MRI — body region and clinical indication mismatch. Flag as probable coding error.",
     "CMS", "LCD L35031 — MRI Brain", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.90, "Clinical consensus — body region mismatch", "mandatory"),
    ("70553", "I10", "excluded",
     "Hypertension alone does not justify brain MRI. Neurological indication or documented complication (hypertensive encephalopathy) required.",
     "CMS", "LCD L35031 — MRI Brain", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.75, "Guideline-based", "guideline"),

    # ── 72148 (Lumbar Spine MRI) ──────────────────────────────────────────
    ("72148", "M54.5", "required",
     "Low back pain with documented red flags or failure of conservative therapy (6 weeks) — primary indication for lumbar MRI.",
     "CMS", "LCD L35031 — Lumbar Spine MRI", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.90, "CMS MAC LCD for lumbar MRI", "mandatory"),
    ("72148", "S82.001A", "supporting",
     "Patellar fracture — lumbar MRI may be indicated if spinal injury is also suspected. Supporting only.",
     "CMS", "LCD L35031 — Lumbar Spine MRI", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.60, "Clinical judgment — not primary indication", "guideline"),
    ("72148", "I25.10", "excluded",
     "Stable CAD does not justify lumbar spine MRI. Spinal or neurological indication required.",
     "CMS", "LCD L35031 — Lumbar Spine MRI", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.85, "Clinical consensus", "mandatory"),

    # ── PT codes (97110, 97530) ───────────────────────────────────────────
    ("97110", "M17.11", "required",
     "Knee OA — therapeutic exercise is first-line conservative treatment. PT plan of care required.",
     "CMS", "LCD L33631 — Physical Therapy", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.90, "CMS MAC LCD for PT", "mandatory"),
    ("97110", "M17.12", "required",
     "Left knee OA — same PT indication as M17.11.",
     "CMS", "LCD L33631 — Physical Therapy", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.90, "CMS MAC LCD for PT", "mandatory"),
    ("97110", "S82.001A", "supporting",
     "Post-fracture rehabilitation — PT exercises appropriate after acute phase.",
     "CMS", "LCD L33631 — Physical Therapy", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.85, "CMS MAC LCD supporting criteria", "guideline"),
    ("97110", "I25.10", "excluded",
     "Stable CAD alone does not justify therapeutic PT exercises. Cardiac rehabilitation is a distinct service (93797/93798). Flag if PT is billed with cardiac-only DX.",
     "CMS", "LCD L33631 — Physical Therapy", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.80, "Clinical consensus — separate program", "mandatory"),
    ("97530", "M54.5", "supporting",
     "Low back pain — functional activity training is appropriate PT modality.",
     "CMS", "LCD L33631 — Physical Therapy", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.85, "CMS MAC LCD", "guideline"),
    ("97530", "I21.09", "excluded",
     "Acute MI does not justify therapeutic activity PT billing. Cardiac rehab is billed separately (93797/93798). Billing 97530 with acute MI DX suggests either wrong code or wrong DX.",
     "CMS", "LCD L33631 — Physical Therapy", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.85, "Clinical consensus", "mandatory"),

    # ── E&M upcoding patterns ─────────────────────────────────────────────
    ("99215", "Z00.00", "excluded",
     "Wellness encounter (Z00.00) cannot support high-complexity E&M. Preventive visits are billed with 99395-99397. Billing 99215 with Z00.00 is a classic upcoding pattern.",
     "AMA", "CPT E&M Guidelines 2021", AMA_URL, "2025-01-01",
     0.90, "AMA E&M coding guidelines", "mandatory"),
    ("99285", "Z00.00", "excluded",
     "Routine wellness exam does not constitute a high-complexity ED visit. ED level 5 requires documented high MDM with therapeutic decisions.",
     "AMA", "CPT E&M Guidelines 2021", AMA_URL, "2025-01-01",
     0.85, "AMA E&M coding guidelines", "mandatory"),

    # ── ECG ───────────────────────────────────────────────────────────────
    ("93000", "I25.10", "supporting",
     "ECG appropriate for cardiac monitoring in CAD patients.",
     "CMS", "LCD for ECG", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.85, "CMS LCD", "guideline"),
    ("93000", "M54.5", "excluded",
     "Low back pain does not justify ECG. Cardiac indication required.",
     "CMS", "LCD for ECG", "https://www.cms.gov/medicare/coverage/lcds", "2025-01-01",
     0.70, "Clinical consensus", "guideline"),
]


def run(db_path: str = DB_PATH) -> int:
    conn = sqlite3.connect(db_path)
    total = 0
    try:
        if conn.execute("SELECT COUNT(*) FROM cpt_codes").fetchone()[0]:
            print("  code tables already seeded — skipping")
            return 0

        # CPT codes
        for row in CPT_CODES:
            (code, desc, ctype, tier, risk, units, auth, spec,
             add_on, gp_days, eff, term, notes,
             src_auth, src_doc, src_url, reviewed,
             confidence, conf_notes, certainty) = row
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
        total += len(CPT_CODES)

        # ICD codes
        for row in ICD_CODES:
            (code, desc, ctype, tier, chapter, manif, etiol,
             setting, valid_pdx,
             eff, term, notes,
             src_auth, src_doc, src_url, reviewed,
             confidence, conf_notes, certainty) = row
            conn.execute(
                "INSERT INTO icd_codes "
                "(icd_code_id, code, description, code_type, value_tier, chapter, "
                "is_manifestation, is_etiology, typical_setting, valid_as_inpatient_pdx, "
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
        total += len(ICD_CODES)

        # DRG codes
        for row in DRG_CODES:
            (code, desc, dtype, mdc, mdc_desc, weight, gmlos, amlos,
             surgical, eff_fy, term_fy, criteria,
             src_auth, src_doc, src_url, reviewed,
             confidence, conf_notes, certainty) = row
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
        total += len(DRG_CODES)

        # Modifier codes
        for row in MODIFIER_CODES:
            (code, desc, mtype, applies, impact, factor,
             ncci, req_doc, risk_score, valid_pfx, mutex, notes,
             src_auth, src_doc, src_url, reviewed,
             confidence, conf_notes, certainty) = row
            conn.execute(
                "INSERT INTO modifier_codes "
                "(modifier_code_id, code, description, modifier_type, applies_to, "
                "payment_impact, payment_factor, ncci_override, requires_documentation, "
                "audit_risk_score, valid_cpt_prefixes, mutually_exclusive_with, audit_notes, "
                "source_authority, source_document, source_url, last_reviewed_at, "
                "data_confidence, data_confidence_notes, rule_certainty, "
                "created_at, updated_at) VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (str(uuid4()), code, desc, mtype, applies,
                 impact, factor, int(ncci), int(req_doc), risk_score,
                 valid_pfx, mutex, notes,
                 src_auth, src_doc, src_url, reviewed,
                 confidence, conf_notes, certainty, NOW, NOW),
            )
        total += len(MODIFIER_CODES)

        # CPT-modifier map
        for row in CPT_MODIFIER_MAP:
            (cpt, mod, factor, ncci, notes,
             src_auth, src_doc, src_url, reviewed,
             confidence, conf_notes, certainty) = row
            conn.execute(
                "INSERT INTO cpt_modifier_map "
                "(cpt_code, modifier_code, payment_factor, ncci_override, notes, "
                "source_authority, source_document, source_url, last_reviewed_at, "
                "data_confidence, data_confidence_notes, rule_certainty) VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?)",
                (cpt, mod, factor, int(ncci), notes,
                 src_auth, src_doc, src_url, reviewed,
                 confidence, conf_notes, certainty),
            )
        total += len(CPT_MODIFIER_MAP)

        # CPT-DX coverage
        for row in CPT_DX_COVERAGE:
            (cpt, icd, ctype, rationale,
             src_auth, src_doc, src_url, reviewed,
             confidence, conf_notes, certainty) = row
            conn.execute(
                "INSERT INTO cpt_dx_coverage "
                "(cpt_code, icd_code, coverage_type, rationale, "
                "source_authority, source_document, source_url, last_reviewed_at, "
                "data_confidence, data_confidence_notes, rule_certainty) VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?)",
                (cpt, icd, ctype, rationale,
                 src_auth, src_doc, src_url, reviewed,
                 confidence, conf_notes, certainty),
            )
        total += len(CPT_DX_COVERAGE)

        conn.commit()
        print(f"  Inserted {len(CPT_CODES)} CPTs, {len(ICD_CODES)} ICDs, "
              f"{len(DRG_CODES)} DRGs, {len(MODIFIER_CODES)} modifiers, "
              f"{len(CPT_MODIFIER_MAP)} CPT-modifier pairs, "
              f"{len(CPT_DX_COVERAGE)} CPT-DX coverage rules")
        return total
    finally:
        conn.close()


if __name__ == "__main__":
    run()
