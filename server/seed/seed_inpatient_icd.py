"""Upsert 25 inpatient / UB-04 ICD-10-CM codes.

Source basis: CMS MedPAR, AHRQ HCUP, AHA Hospital Statistics, CMS ICD-10-CM 2025.
Codes are heavily represented in facility inpatient claims and are common
DRG severity drivers, RAC targets, and HAC candidates.

Run standalone:  python seed/seed_inpatient_icd.py
Or via seed_all:  imported and called in the appropriate step.

Uses INSERT OR IGNORE + UPDATE so it is safe to run repeatedly.
For the 4 codes already seeded with outpatient context (I25.10, I10, E11.9,
J18.9) the script updates audit_notes to add inpatient/DRG framing while
leaving all other fields intact if they already carry higher-quality data.
"""
from __future__ import annotations

import os
import sqlite3
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW = "2025-01-01T00:00:00"

SRC_AUTH = "CMS"
SRC_DOC  = "ICD-10-CM 2025"
SRC_URL  = "https://www.cms.gov/medicare/coding-billing/icd-10-codes"
REVIEWED = "2025-01-01"
CONF     = 0.95
CONF_NOTE = "CMS ICD-10-CM 2025 tabular; inpatient DRG context from CMS MedPAR / AHRQ HCUP"

# (code, description, value_tier, chapter, is_manifestation, is_etiology, audit_notes)
CODES = [
    # ── MCC / High-severity ────────────────────────────────────────────────
    (
        "A41.9",
        "Sepsis, unspecified organism",
        "high",
        "Certain Infectious and Parasitic Diseases",
        False, False,
        "High-dollar; DRG 870 (without MCC), 871 (with CC), 872 (with MCC). "
        "Sepsis is the #1 most expensive diagnosis in US hospitals. "
        "Requires clinical criteria (SOFA ≥2 + suspected infection source), blood cultures, IV antibiotics, and IV fluids. "
        "A41.9 is unspecified organism — code more specifically when organism is identified (e.g., A41.01 MRSA, A41.59 gram-negative). "
        "RAC target: distinguish sepsis (Sepsis-3 criteria) from SIRS (R65.10/11). "
        "Physician must document 'sepsis' in the record — nursing or ancillary notes alone are insufficient. "
        "Septic shock (R65.21) is an MCC and must be explicitly documented."
    ),
    (
        "G93.41",
        "Metabolic encephalopathy",
        "high",
        "Diseases of the Nervous System",
        False, False,
        "MCC — major DRG severity driver across many inpatient DRGs. "
        "G93.41 is among the most common MCCs added to inpatient records. "
        "Requires explicit physician documentation of 'metabolic encephalopathy' — "
        "'altered mental status', 'confusion', or 'AMS' alone are insufficient. "
        "Must have documented metabolic etiology (hepatic, uremic, hypoxic, toxic). "
        "Distinguish from delirium (F05) — both can coexist; query physician when documentation is ambiguous. "
        "Common upcoding concern in outlier DRG cases. High RAC and MAC audit frequency. "
        "Verify the underlying metabolic cause is also coded and documented."
    ),
    (
        "J96.00",
        "Acute respiratory failure, unspecified whether with hypoxia or hypercapnia",
        "high",
        "Diseases of the Respiratory System",
        False, False,
        "MCC — significant DRG severity driver. DRG 189 as principal DX. "
        "As secondary DX dramatically elevates DRG weight (e.g., adds MCC tier to DRG 871, 291, 193). "
        "Requires documented respiratory failure — not just SpO2 desaturation. "
        "Typical criteria: PaO2 <60 mmHg on room air, PCO2 >50 mmHg with acidosis, or requiring mechanical ventilation. "
        "J96.00 is unspecified — specify J96.01 (hypoxic) or J96.02 (hypercapnic) when ABG results and physician documentation support it. "
        "Mechanical ventilation (5A1935Z, 5A1945Z) is a separate procedure code. "
        "Common audit finding: J96.0x coded without arterial blood gas or explicit physician documentation of respiratory failure."
    ),
    (
        "T81.40XA",
        "Infection following a procedure, unspecified, initial encounter",
        "high",
        "Injury, Poisoning and Certain Other Consequences of External Causes",
        False, False,
        "Complication code — HAC (Hospital-Acquired Condition) with CMS payment penalty implications. "
        "T81.40XA is initial encounter ('A' 7th character). "
        "Requires physician-documented causal link between the procedure and the infection — temporal proximity alone is insufficient. "
        "Specify infection type when known: T81.41XA (SSI), T81.42XA (post-procedure pneumonia), T81.43XA (post-procedure sepsis). "
        "Common audit target: causality must be physician-established; coding from POA indicator is critical. "
        "If present on admission (POA = Y), not an HAC — verify POA assignment. "
        "Organism should be coded additionally (B95-B96, A41.x for sepsis). "
        "Common RAC target for complication coding accuracy."
    ),
    (
        "N17.9",
        "Acute kidney injury, unspecified",
        "high",
        "Diseases of the Genitourinary System",
        False, False,
        "DRG 682 (with MCC), 683 (with CC), 684 (without). Commonly coded as CC/MCC as secondary DX. "
        "Requires explicit physician documentation — creatinine elevation alone is insufficient without physician diagnosis. "
        "Distinguish AKI (N17.x) from CKD (N18.x) — AKI on CKD coded N17.9 + N18.x. "
        "Stage AKI when documented (N17.0 tubular necrosis, N17.1 acute cortical necrosis, N17.2 medullary necrosis). "
        "Verify treating physician documented AKI/ARF — lab values alone do not justify coding. "
        "KDIGO criteria (creatinine rise ≥0.3 mg/dL in 48h or ≥1.5× baseline in 7 days) support but do not replace physician diagnosis. "
        "Common RAC/MAC target: AKI coded from lab trend without physician documentation."
    ),
    (
        "I26.99",
        "Other pulmonary embolism without acute cor pulmonale",
        "high",
        "Diseases of the Circulatory System",
        False, False,
        "DRG 175 (with MCC), 176 (without). "
        "I26.99 is without acute cor pulmonale. I26.09 includes acute cor pulmonale (MCC). "
        "Diagnosis requires imaging confirmation: CTPA, V/Q scan, or echocardiographic evidence. "
        "Specify acute vs chronic (I27.82 for chronic thromboembolic PE). "
        "DVT often coded concurrently (I82.4xx — specify laterality and vessel). "
        "Submassive PE with RV strain may support cor pulmonale documentation — query physician. "
        "Thrombolysis and catheter-directed therapy are procedure codes. "
        "Anticoagulation start codes Z79.01 (long-term). "
        "Common audit: PE coded without imaging confirmation or incorrectly coded as chronic."
    ),
    (
        "I63.9",
        "Cerebral infarction, unspecified",
        "high",
        "Diseases of the Circulatory System",
        False, False,
        "DRG 061 (with thrombolysis, MCC), 062 (with MCC), 063 (with CC), 064–066. "
        "Requires CT or MRI imaging confirmation of infarction. "
        "I63.9 is unspecified — specify arterial territory and laterality when documented "
        "(I63.3x MCA, I63.4x anterior cerebral, I63.5x other specified cerebral). "
        "Distinguish ischemic stroke (I63.x) from hemorrhagic (I60-I62), TIA (G45.9 — no infarct), or intracerebral hemorrhage (I61.x). "
        "tPA administration codes to 3E033GC and elevates to DRG 061 tier. "
        "Neurological deficit at discharge should be coded (hemiplegia I69.35x, aphasia I69.320). "
        "High RAC audit frequency — verify radiology report confirms infarction."
    ),
    (
        "S72.001A",
        "Fracture of unspecified part of neck of right femur, initial encounter for closed fracture",
        "high",
        "Injury, Poisoning and Certain Other Consequences of External Causes",
        False, False,
        "DRG 480 (with MCC), 481 (with CC), 482 (without). High-dollar orthopedic admission. "
        "S72.001A is 7th character 'A' (initial encounter for closed fracture). "
        "Specify laterality: S72.001A (right), S72.002A (left), S72.009A (unspecified). "
        "Open fracture 7th characters: B–F based on Gustilo-Anderson classification. "
        "Surgical repair (ORIF, hemiarthroplasty, total hip arthroplasty) significantly affects DRG grouping. "
        "Fall mechanism coded additionally (W18.xxXA, W19.xxXA). "
        "Pathological fracture from osteoporosis codes differently (M80.x51A). "
        "Common audit: 7th character accuracy — 'A' only for initial active treatment encounter; "
        "subsequent care is 'D' or 'G' through 'S' (sequela). "
        "CC/MCC coding (delirium, AKI, respiratory failure) dramatically affects DRG weight."
    ),
    (
        "K92.1",
        "Melena",
        "high",
        "Diseases of the Digestive System",
        False, False,
        "DRG 377 (with MCC), 378 (with CC), 379 (without). "
        "Melena indicates upper GI bleed (dark tarry stool from digested blood). "
        "K92.1 is a symptom code — add underlying etiology when identified by endoscopy "
        "(K25.x peptic ulcer, K57.x diverticular, K22.6 Mallory-Weiss). "
        "When the specific bleeding source is identified, it should be sequenced as principal DX. "
        "Hemoglobin drop and clinical symptoms required — not from stool guaiac alone. "
        "Transfusion (30233N1 packed RBCs) coded separately. "
        "Common audit finding: melena coded as principal when a specific bleeding source was identified endoscopically."
    ),
    (
        "A04.72",
        "Enterocolitis due to Clostridium difficile, not specified as recurrent",
        "high",
        "Certain Infectious and Parasitic Diseases",
        False, False,
        "DRG 371 (with MCC), 372 (with CC), 373 (without). "
        "A04.71 = recurrent (prior episode within 8 weeks). A04.72 = not recurrent or unspecified. "
        "Requires positive C. diff toxin assay (PCR or EIA) and clinical symptoms (diarrhea ≥3 loose stools/day). "
        "Fulminant C. diff (megacolon, perforation, ICU admission) is MCC driver. "
        "Treatment: oral vancomycin or fidaxomicin; fidaxomicin for recurrent. "
        "Contact precautions required — verify infection control documentation. "
        "Distinguish from carrier state (positive test without symptoms — should not be coded as active infection). "
        "Common audit: distinguish A04.71 vs A04.72 — affects DRG and treatment intensity documentation."
    ),
    (
        "C34.90",
        "Malignant neoplasm of bronchus and lung, unspecified, unspecified side",
        "high",
        "Neoplasms",
        False, False,
        "DRG 582 (with MCC), 583 (with CC), 584 (without) for primary lung malignancy. "
        "C34.90 is unspecified site and laterality — code with site (C34.1x upper lobe, C34.2 middle, C34.3x lower) "
        "and laterality (1=right, 2=left) when documented. "
        "Secondary/metastatic lung malignancy codes C78.00 (unspecified), C78.01 (right), C78.02 (left). "
        "Histologic type should be identified from pathology (NSCLC vs SCLC affects staging and treatment). "
        "Code chemotherapy (Z79.899), immunotherapy (Z79.899), or radiation (Z51.0) as applicable. "
        "Active malignancy vs history (Z85.118) sequencing is critical — affects DRG and medical necessity."
    ),
    (
        "K57.30",
        "Diverticulosis of large intestine without perforation or abscess without bleeding",
        "high",
        "Diseases of the Digestive System",
        False, False,
        "DRG 391/392 for diverticulitis without complication. "
        "K57.30 = diverticulosis large intestine, no abscess/perforation, no bleeding. "
        "Diverticulitis with abscess codes K57.20 (small intestine) or K57.32 (large intestine). "
        "Perforation dramatically increases severity — K57.20/32 with peritonitis. "
        "Bleeding codes: K57.31 (large intestine with bleeding). "
        "CT confirmation distinguishes diverticulitis from diverticulosis. "
        "Antibiotics, IV fluids, bowel rest are standard inpatient management. "
        "Drainage procedure or surgery codes change DRG. "
        "Common audit: verify CT report and surgical findings confirm diverticulitis (not just diverticulosis)."
    ),
    # ── Moderate acuity ────────────────────────────────────────────────────
    (
        "I50.9",
        "Heart failure, unspecified",
        "moderate",
        "Diseases of the Circulatory System",
        False, False,
        "DRG 291 (with MCC), 292 (with CC), 293 (without). "
        "I50.9 is unspecified — specify systolic vs diastolic and acute/chronic/acute-on-chronic: "
        "I50.22 chronic systolic, I50.23 acute-on-chronic systolic; I50.32 chronic diastolic, I50.33 acute-on-chronic diastolic. "
        "Specificity improves clinical documentation and DRG accuracy. "
        "BNP/NT-proBNP documentation supports diagnosis. EF from echo should be noted. "
        "LVEF ≤40% = reduced (HFrEF); LVEF ≥50% = preserved (HFpEF); 41-49% = mildly reduced. "
        "CC/MCC coding (AKI, respiratory failure, sepsis) significantly affects DRG weight. "
        "Verify comorbidities are documented and treated during the stay."
    ),
    (
        "I21.9",
        "Acute myocardial infarction, unspecified",
        "high",
        "Diseases of the Circulatory System",
        False, False,
        "DRG 280 (with MCC), 281 (with CC), 282 (without). "
        "I21.9 is unspecified — should be coded as STEMI (I21.0x-I21.2x) or NSTEMI (I21.4) when documented. "
        "Type 2 MI (supply-demand mismatch, no plaque rupture) codes I21.A1 — distinguish from type 1. "
        "Troponin elevation + EKG changes + clinical context required for AMI diagnosis. "
        "Cath lab report should confirm vessel involvement for STEMI specificity. "
        "PCI procedure (027x04Z, 027x0ZZ by vessel) and stent type affect DRG. "
        "Common audit: Type 1 vs Type 2 MI distinction — affects treatment, workup, and coding."
    ),
    (
        "I48.91",
        "Unspecified atrial fibrillation",
        "moderate",
        "Diseases of the Circulatory System",
        False, False,
        "DRG 308 (with MCC), 309 (with CC), 310 (without) when AF is principal DX. "
        "I48.91 is unspecified — specify when documented: I48.0 paroxysmal (self-terminates <7 days), "
        "I48.11 longstanding persistent, I48.19 other persistent, I48.20 chronic (permanent). "
        "Cardioversion (5A2204Z electrical, 5A12012 chemical) coded separately. "
        "Rate vs rhythm control strategy should be documented. "
        "When AF is incidental to a primary condition (e.g., COPD exacerbation), sequence appropriately. "
        "CHA2DS2-VASc score and anticoagulation management should be documented for medical necessity."
    ),
    (
        "Z51.11",
        "Encounter for antineoplastic chemotherapy",
        "moderate",
        "Factors Influencing Health Status",
        False, False,
        "DRG 847 (with MCC), 848 (with CC). "
        "Z51.11 is sequenced as PRINCIPAL DX when admission is primarily for chemotherapy administration. "
        "The neoplasm is sequenced as secondary DX (active malignancy C-code). "
        "Chemotherapy agent and administration route coded separately. "
        "Complications of chemo (N&V = R11.x, neutropenia = D70.1) coded additionally when documented and treated. "
        "Common audit: verify Z51.11 is appropriate as principal — only when admission is specifically for chemo delivery. "
        "If patient admitted for a complication of chemo, the complication is principal and Z51.11 is secondary."
    ),
    # ── CC / Secondary diagnoses ───────────────────────────────────────────
    (
        "N39.0",
        "Urinary tract infection, site not specified",
        "low",
        "Diseases of the Genitourinary System",
        False, False,
        "DRG 689 (with MCC/CC), 690 (without). "
        "Among the most commonly overcoded diagnoses in inpatient billing. "
        "Requires positive urine culture (or documented clinical diagnosis) AND physician documentation of UTI. "
        "Asymptomatic bacteriuria (R82.71) must NOT be coded as N39.0 — requires clinical symptoms. "
        "Distinguish from catheter-associated UTI (T83.511A initial). "
        "If UTI is the only diagnosis, verify it truly required inpatient level of care vs observation. "
        "Common audit finding: UTI coded solely from positive urine culture without treating physician diagnosis. "
        "Organism should be coded additionally when identified (B96.x, E. coli = B96.20)."
    ),
    (
        "J44.1",
        "Chronic obstructive pulmonary disease with (acute) exacerbation",
        "high",
        "Diseases of the Respiratory System",
        False, False,
        "DRG 190 (with MCC), 191 (with CC), 192 (without). "
        "Requires documented acute exacerbation — worsening dyspnea, increased sputum, change in sputum character. "
        "J44.0 = COPD with acute lower respiratory infection (add J12-J18 for the infection). "
        "J44.1 = exacerbation without specified acute infection. "
        "Common MCC pairing: acute respiratory failure (J96.00/01). "
        "Spirometry not required for inpatient coding but supports documentation. "
        "Treatment (bronchodilators, steroids, O2) should be documented. "
        "Verify pulmonary function history and response to treatment in the record."
    ),
    (
        "E87.6",
        "Hypokalemia",
        "low",
        "Endocrine, Nutritional and Metabolic Diseases",
        False, False,
        "Secondary CC in inpatient setting. "
        "K+ <3.5 mEq/L — common electrolyte abnormality. "
        "Must be documented by treating physician AND treated (IV or oral K+ replacement) during the stay. "
        "Should not be coded solely from lab values without physician documentation. "
        "Hypokalemia as isolated finding does not justify inpatient admission alone. "
        "Paired frequently with diuretic therapy, GI losses, poor intake, hyperaldosteronism. "
        "Severe hypokalemia (<2.5 mEq/L) with cardiac manifestations is higher acuity."
    ),
    (
        "D64.9",
        "Anemia, unspecified",
        "low",
        "Diseases of the Blood and Blood-forming Organs",
        False, False,
        "Secondary CC. "
        "D64.9 is unspecified — specify when documented: D50.9 iron deficiency, D51.0 B12 deficiency, "
        "D64.81 anemia in neoplastic disease, D62 acute blood loss anemia (important for GI bleed cases). "
        "Must be documented by physician AND treated (transfusion, IV iron, erythropoiesis-stimulating agents). "
        "Common audit: D64.9 coded from Hgb <10 without physician documentation. "
        "Blood transfusion coded separately (30233N1 leukoreduced RBCs, 30233R1 irradiated). "
        "Anemia in chronic disease (D63.1) from CKD coded additionally with the CKD."
    ),
    (
        "B96.81",
        "Helicobacter pylori [H. pylori] as the cause of diseases classified elsewhere",
        "low",
        "Certain Infectious and Parasitic Diseases",
        False, False,
        "Secondary diagnosis — add-on to upper GI conditions (K25.x peptic ulcer, K92.1 GI bleed, K29.x gastritis). "
        "Requires documented positive H. pylori test: CLO test (rapid urease), urea breath test, stool antigen, or biopsy. "
        "Not typically a principal DX on its own. "
        "H. pylori eradication therapy (PPI + clarithromycin + amoxicillin or metronidazole triple therapy) "
        "should be documented when coded. "
        "Verify the lab/pathology result is in the medical record."
    ),
    (
        "Z51.11",
        "Encounter for antineoplastic chemotherapy",
        "moderate",
        "Factors Influencing Health Status",
        False, False,
        "DRG 847 (with MCC), 848 (with CC). "
        "Z51.11 sequenced as PRINCIPAL DX when admission is primarily for chemotherapy. "
        "Neoplasm is secondary DX. Chemo agent and administration route coded separately. "
        "Complications of chemo (nausea/vomiting, neutropenia) coded when documented and treated. "
        "Verify Z51.11 is appropriate as principal — if admitted for a complication of chemo, "
        "the complication is principal and Z51.11 is secondary.",
    ),
]

# Deduplicate (Z51.11 was listed twice above — remove the duplicate)
seen: dict[str, tuple] = {}
for row in CODES:
    seen[row[0]] = row
CODES = list(seen.values())

# ── Codes already in seed with outpatient context — update audit_notes ─────────
UPDATES = {
    "I25.10": (
        "Stable CAD — DRG 302 (with MCC), 303 (with CC), 304 (without) as principal inpatient DX. "
        "Also valid cardiac indication for echo, stress test, and cath. "
        "Does not alone justify PT or musculoskeletal procedures in either inpatient or outpatient setting. "
        "Inpatient: verify that CAD was the primary reason for admission (not incidental comorbidity). "
        "Common secondary DX in PCI/CABG admissions."
    ),
    "I10": (
        "Essential hypertension — secondary DX in inpatient setting. "
        "I10 alone has minimal DRG weight but contributes to CC count when documented and treated. "
        "Hypertension with heart disease codes I11.x; with CKD codes I13.x; with both I13.1x. "
        "Should be documented as a condition monitored and/or treated during the stay. "
        "Secondary hypertension (renovascular I15.0, endocrine I15.1-I15.8) codes to I15.x. "
        "Common audit: I10 overcoded as MCC/CC when it adds little to the admission complexity."
    ),
    "E11.9": (
        "Type 2 diabetes without complications — secondary DX in inpatient setting. "
        "Affects CC/MCC severity when complications are coded (E11.40 neuropathy, E11.65 nephropathy, E11.31x retinopathy). "
        "Poorly controlled DM = E11.649. Insulin use coded separately Z79.4. "
        "Cannot be inferred from glucose values alone — requires physician documentation. "
        "Secondary CC that elevates DRG weight when documented and actively managed during stay. "
        "DRG impact: adds CC tier to many medical DRGs when sequenced correctly."
    ),
    "J18.9": (
        "Pneumonia — DRG 193 (with MCC), 194 (with CC), 195 (without). "
        "Requires clinical diagnosis by physician — not solely from imaging infiltrate. "
        "Specify organism when identified: J15.x bacterial, J12.x viral, J16.x other specified organism. "
        "Ventilator-associated pneumonia codes J95.851 (not J18.9). "
        "Common MCC pairing: sepsis (A41.9) from pneumonia; acute respiratory failure (J96.00). "
        "Verify CXR/CT report AND treating physician documentation. "
        "Chest imaging alone without physician diagnosis is insufficient."
    ),
}


def run(db_path: str = DB_PATH) -> int:
    conn = sqlite3.connect(db_path)
    inserted = updated = 0
    try:
        for row in CODES:
            code, desc, tier, chapter, manif, etiol, notes = row
            # Try insert — skip if code already exists
            conn.execute(
                "INSERT OR IGNORE INTO icd_codes "
                "(icd_code_id, code, description, code_type, value_tier, chapter, "
                "is_manifestation, is_etiology, typical_setting, valid_as_primary_dx, "
                "effective_date, termination_date, audit_notes, "
                "source_authority, source_document, source_url, last_reviewed_at, "
                "data_confidence, data_confidence_notes, rule_certainty, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (str(uuid4()), code, desc, "icd10_cm", tier, chapter,
                 int(manif), int(etiol), "inpatient", 1,
                 "2024-10-01", None, notes,
                 SRC_AUTH, SRC_DOC, SRC_URL, REVIEWED,
                 CONF, CONF_NOTE, "mandatory", NOW, NOW),
            )
            if conn.execute("SELECT changes()").fetchone()[0]:
                inserted += 1
            else:
                # Code exists — update only audit_notes if this seed provides richer content
                conn.execute(
                    "UPDATE icd_codes SET audit_notes = ?, last_reviewed_at = ?, updated_at = ? "
                    "WHERE code = ? AND (audit_notes IS NULL OR length(audit_notes) < length(?))",
                    (notes, REVIEWED, NOW, code, notes),
                )
                if conn.execute("SELECT changes()").fetchone()[0]:
                    updated += 1

        # Targeted audit_notes updates for pre-existing outpatient-focused codes
        for code, notes in UPDATES.items():
            conn.execute(
                "UPDATE icd_codes SET audit_notes = ?, last_reviewed_at = ?, updated_at = ? WHERE code = ?",
                (notes, REVIEWED, NOW, code),
            )
            if conn.execute("SELECT changes()").fetchone()[0]:
                updated += 1

        conn.commit()
        total = len(CODES) + len(UPDATES)
        print(f"  Inpatient ICD-10: {inserted} inserted, {updated} updated ({total} total processed)")
        return inserted + updated
    finally:
        conn.close()


if __name__ == "__main__":
    run()
