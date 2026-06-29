"""Upsert 85 ICD-10-CM codes across hospital inpatient, outpatient, professional,
SNF, home health, IRF, and sleep study settings.

Source: Claude (claude.ai) structured output with all columns specified,
validated against ICD-10-CM 2025 tabular, CMS MedPAR, AHRQ HCUP, and
setting-specific LCD/coverage documentation.

Run standalone:  python seed/seed_extended_icd.py
"""
from __future__ import annotations

import json
import os
import sqlite3
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW = "2025-01-01T00:00:00"

# ── Chapter lookup by code prefix ─────────────────────────────────────────────

def _chapter(code: str) -> str:
    c = code[0].upper()
    return {
        'A': 'Certain Infectious and Parasitic Diseases',
        'B': 'Certain Infectious and Parasitic Diseases',
        'C': 'Neoplasms',
        'D': 'Diseases of the Blood and Blood-forming Organs' if code[:2] >= 'D5' else 'Neoplasms',
        'E': 'Endocrine, Nutritional and Metabolic Diseases',
        'F': 'Mental, Behavioral and Neurodevelopmental Disorders',
        'G': 'Diseases of the Nervous System',
        'H': 'Diseases of the Eye and Adnexa' if code[:2] <= 'H59' else 'Diseases of the Ear and Mastoid Process',
        'I': 'Diseases of the Circulatory System',
        'J': 'Diseases of the Respiratory System',
        'K': 'Diseases of the Digestive System',
        'L': 'Diseases of the Skin and Subcutaneous Tissue',
        'M': 'Diseases of the Musculoskeletal System and Connective Tissue',
        'N': 'Diseases of the Genitourinary System',
        'O': 'Pregnancy, Childbirth and the Puerperium',
        'P': 'Certain Conditions Originating in the Perinatal Period',
        'Q': 'Congenital Malformations, Deformations and Chromosomal Abnormalities',
        'R': 'Symptoms, Signs and Abnormal Clinical and Laboratory Findings',
        'S': 'Injury, Poisoning and Certain Other Consequences of External Causes',
        'T': 'Injury, Poisoning and Certain Other Consequences of External Causes',
        'U': 'Codes for Special Purposes',
        'Z': 'Factors Influencing Health Status and Contact with Health Services',
    }.get(c, 'Other')


# ── Code definitions ───────────────────────────────────────────────────────────
# Each dict: code, description, value_tier, typical_setting, settings (list),
#            valid_as_primary_dx, termination_date (opt), audit_notes,
#            source_document, data_confidence, rule_certainty

CODES = [

    # ── HOSPITAL INPATIENT ─────────────────────────────────────────────────

    dict(code="I11.0", description="Hypertensive heart disease with heart failure",
         value_tier="high", typical_setting="both",
         settings=["inpatient","outpatient","professional"],
         valid_as_primary_dx=True,
         audit_notes="Combination code — when hypertension and heart failure are both documented, "
             "I11.0 MUST be used rather than separately coding I10 + I50.x per ICD-10-CM causal "
             "relationship presumption guidelines. Coding I10 + I50.9 separately is one of the most "
             "common sequencing errors auditors find. Additional code for heart failure type (I50.x) "
             "is still required. Significantly impacts DRG severity (DRG 291–293) and HCC capture.",
         source_document="ICD-10-CM 2025; AHA Coding Clinic 4Q2016; ICD-10-CM Guidelines I.C.9.a",
         data_confidence=0.94, rule_certainty="mandatory"),

    # ── HOSPITAL OUTPATIENT ────────────────────────────────────────────────

    dict(code="Z12.11", description="Encounter for screening for malignant neoplasm of colon",
         value_tier="moderate", typical_setting="outpatient",
         settings=["outpatient","professional"], valid_as_primary_dx=False,
         audit_notes="Highest-volume screening code in hospital outpatient; drives colonoscopy APC 5731. "
             "Critical: when a polyp is found and removed, the encounter becomes diagnostic — Z12.11 "
             "may be dropped and K63.5 added, changing APC and patient cost-sharing. Payer policy varies "
             "on screening-turned-diagnostic. Validate patient screening history against frequency guidelines.",
         source_document="ICD-10-CM 2025; CMS OPPS; ACS Colorectal Screening Guidelines",
         data_confidence=0.96, rule_certainty="mandatory"),

    dict(code="M54.5", description="Low back pain [RETIRED FY2023 — use M54.50/M54.51/M54.59]",
         value_tier="moderate", typical_setting="outpatient",
         settings=["outpatient","professional"], valid_as_primary_dx=False,
         termination_date="2022-09-30",
         audit_notes="RETIRED effective ICD-10-CM FY2023 (DOS on or after Oct 1 2022). "
             "ClaimGuard should flag M54.5 on claims with DOS ≥ 2022-10-01 as an inactive code. "
             "Replaced by M54.50 (unspecified), M54.51 (vertebrogenic), M54.59 (other). "
             "Specificity to vertebrogenic vs radicular drives LCD coverage for epidural steroid injections.",
         source_document="ICD-10-CM 2023 (deleted); superseded by M54.50/51/59",
         data_confidence=0.97, rule_certainty="mandatory"),

    dict(code="M54.50", description="Low back pain, unspecified",
         value_tier="moderate", typical_setting="outpatient",
         settings=["outpatient","professional"], valid_as_primary_dx=False,
         audit_notes="Replacement for retired M54.5 (effective FY2023). High-volume outpatient, urgent care, "
             "and professional. LCDs for spinal procedures require specific back pain codes and documented "
             "conservative treatment failure. Physical therapy and chiropractic frequency limit edits apply.",
         source_document="ICD-10-CM 2025; CMS LCD L33836",
         data_confidence=0.96, rule_certainty="mandatory"),

    dict(code="K21.0", description="Gastro-esophageal reflux disease with esophagitis",
         value_tier="low", typical_setting="outpatient",
         settings=["outpatient","professional"], valid_as_primary_dx=False,
         audit_notes="K21.9 (without esophagitis) when esophagitis not documented. EGD procedures "
             "(43239, 43235) commonly associated; LCD requires documented failure of medical management. "
             "Frequency rules apply to endoscopic surveillance in Barrett's esophagus.",
         source_document="ICD-10-CM 2025; CMS LCD L34010",
         data_confidence=0.92, rule_certainty="guideline"),

    dict(code="F32.9", description="Major depressive disorder, single episode, unspecified",
         value_tier="moderate", typical_setting="outpatient",
         settings=["outpatient","professional"], valid_as_primary_dx=False,
         audit_notes="High-volume behavioral health outpatient. Severity specifiers (mild F32.0, moderate "
             "F32.1, severe F32.2) should be used when documented. MHPAEA parity requirements make mental "
             "health audits sensitive. Telehealth behavioral health claims have been a major audit focus "
             "post-PHE; audio-only documentation requirements must be met.",
         source_document="ICD-10-CM 2025; MHPAEA; CMS Telehealth Policy",
         data_confidence=0.93, rule_certainty="guideline"),

    dict(code="Z12.31", description="Encounter for screening mammogram for malignant neoplasm of breast",
         value_tier="moderate", typical_setting="outpatient",
         settings=["outpatient","professional"], valid_as_primary_dx=False,
         audit_notes="Preventive screening for mammography. Screening (Z12.31) vs diagnostic (Z12.39 or "
             "symptom code) distinction significantly affects APC assignment and patient cost-sharing. "
             "Annual frequency per USPSTF. When findings are present, Z12.31 may be secondary. "
             "3D mammography (tomosynthesis, CPT 77063) has specific coverage requirements.",
         source_document="ICD-10-CM 2025; CMS OPPS; USPSTF Mammography Guidelines",
         data_confidence=0.95, rule_certainty="mandatory"),

    dict(code="H26.9", description="Unspecified cataract",
         value_tier="moderate", typical_setting="outpatient",
         settings=["outpatient","professional"], valid_as_primary_dx=False,
         audit_notes="Pre-operative diagnosis for cataract extraction (CPT 66984, 66982). Medicare covers "
             "when visual acuity documentation supports medical necessity. Specificity (H25.x age-related, "
             "H26.1x traumatic) preferred over H26.9 when type is documented. Premium IOL upgrades are "
             "non-covered and must be separated from the covered surgical claim.",
         source_document="ICD-10-CM 2025; CMS NCD 80.8",
         data_confidence=0.93, rule_certainty="guideline"),

    dict(code="N40.0", description="Benign prostatic hyperplasia without lower urinary tract symptoms",
         value_tier="low", typical_setting="outpatient",
         settings=["outpatient","professional"], valid_as_primary_dx=False,
         audit_notes="N40.1 (with LUTS) when lower urinary tract symptoms are documented — distinction "
             "affects LCD coverage for minimally invasive BPH treatments (UroLift, Rezum, TURP). "
             "Sex-specific — billing N40.x with female beneficiary is an immediate flag.",
         source_document="ICD-10-CM 2025; CMS LCD L37165",
         data_confidence=0.94, rule_certainty="mandatory"),

    dict(code="E78.5", description="Hyperlipidemia, unspecified",
         value_tier="low", typical_setting="outpatient",
         settings=["outpatient","professional"], valid_as_primary_dx=False,
         audit_notes="Extremely high-volume chronic disease code. E78.00 (pure hypercholesterolemia), "
             "E78.1 (hypertriglyceridemia) preferred when documented. Associated with lipid panel "
             "(80061) and statin management. HCC-relevant in Medicare Advantage when associated with "
             "cardiovascular conditions.",
         source_document="ICD-10-CM 2025; CMS HCC Model V28",
         data_confidence=0.96, rule_certainty="guideline"),

    dict(code="R10.9", description="Unspecified abdominal pain",
         value_tier="low", typical_setting="ed",
         settings=["outpatient","professional"], valid_as_primary_dx=False,
         audit_notes="High-volume ED and urgent care symptom code. Should be replaced by specific "
             "diagnosis when etiology is established. Specific quadrant pain codes (R10.1–R10.3) support "
             "imaging medical necessity better than R10.9. Replace with confirmed diagnosis per "
             "ICD-10-CM outpatient coding guidelines when established.",
         source_document="ICD-10-CM 2025; ICD-10-CM Guidelines Section IV",
         data_confidence=0.93, rule_certainty="guideline"),

    dict(code="R55", description="Syncope and collapse",
         value_tier="moderate", typical_setting="ed",
         settings=["outpatient"], valid_as_primary_dx=False,
         audit_notes="High-volume ED code frequently leading to observation or short inpatient stay. "
             "Observation for syncope workup is a common payer audit target — must meet medical necessity. "
             "When etiology is identified (arrhythmia, orthostatic hypotension), specific code replaces R55. "
             "CMS Observation Notice (MOON) requirements apply for observation status.",
         source_document="ICD-10-CM 2025; CMS MOON Requirements; CMS Obs Status Guidelines",
         data_confidence=0.91, rule_certainty="guideline"),

    dict(code="F41.1", description="Generalized anxiety disorder",
         value_tier="low", typical_setting="outpatient",
         settings=["outpatient","professional"], valid_as_primary_dx=False,
         audit_notes="High-volume behavioral health outpatient. MHPAEA parity requirements apply. "
             "Telehealth behavioral health (audio-only) is an active post-PHE audit area. "
             "Psychotherapy CPTs (90832–90838) must reconcile with documented session length and "
             "treatment necessity.",
         source_document="ICD-10-CM 2025; MHPAEA; CMS PHE Telehealth Extensions",
         data_confidence=0.93, rule_certainty="guideline"),

    # ── PROFESSIONAL (CMS-1500) ────────────────────────────────────────────

    dict(code="Z23", description="Encounter for immunization",
         value_tier="low", typical_setting="outpatient",
         settings=["professional","outpatient"], valid_as_primary_dx=False,
         audit_notes="Standard vaccine encounter paired with administration CPTs (90460, 90471) and the "
             "vaccine product HCPCS code. Medicare Part B covers flu (Q2034–Q2039), pneumococcal (90670, "
             "90732), and COVID vaccines with specific coding requirements. Bundling Z23 with sick-visit "
             "E&M requires modifier 25 on the E&M.",
         source_document="ICD-10-CM 2025; CMS Medicare Preventive Services",
         data_confidence=0.95, rule_certainty="mandatory"),

    dict(code="J06.9", description="Acute upper respiratory infection, unspecified",
         value_tier="low", typical_setting="outpatient",
         settings=["professional","outpatient"], valid_as_primary_dx=False,
         audit_notes="Highest-volume acute illness code in PCP and urgent care. Antibiotic prescribing "
             "with J06.9 is a clinical quality flag — URIs are viral per HEDIS/NCQA measure AAB. "
             "High-volume telehealth diagnosis post-COVID PHE; audio-only documentation requirements. "
             "Specific URI subtypes (J00 common cold) preferred when documented.",
         source_document="ICD-10-CM 2025; NCQA HEDIS Measure AAB",
         data_confidence=0.96, rule_certainty="guideline"),

    dict(code="J45.20", description="Mild intermittent asthma, uncomplicated",
         value_tier="low", typical_setting="outpatient",
         settings=["professional","outpatient","home_health"], valid_as_primary_dx=False,
         audit_notes="Asthma requires severity and frequency specificity — intermittent vs persistent, "
             "uncomplicated vs acute exacerbation vs status asthmaticus. Must be consistent with "
             "documented symptom frequency and PFT/spirometry. Associated inhaler prescriptions and "
             "nebulizer claims must align with documented severity.",
         source_document="ICD-10-CM 2025; NAEPP Asthma Guidelines",
         data_confidence=0.92, rule_certainty="guideline"),

    dict(code="M54.2", description="Cervicalgia",
         value_tier="low", typical_setting="outpatient",
         settings=["professional","outpatient"], valid_as_primary_dx=False,
         audit_notes="High-volume musculoskeletal code in PCP, orthopedics, and pain management. "
             "Cervical spine MRI (72141/72142) requires documented clinical indications per LCD. "
             "Cervical epidural steroid injections (CPT 62321) require documented radiculopathy and "
             "failed conservative treatment. Physical therapy frequency limits apply.",
         source_document="ICD-10-CM 2025; CMS LCD L34010",
         data_confidence=0.91, rule_certainty="guideline"),

    dict(code="Z79.01", description="Long-term (current) use of anticoagulants",
         value_tier="low", typical_setting="both",
         settings=["professional","outpatient","inpatient"], valid_as_primary_dx=False,
         audit_notes="Status code — never a principal diagnosis but clinically important secondary. "
             "Required for anticoagulant monitoring services (INR 85610). CMS requires Z79.01 on claims "
             "for anticoagulant reversal agents. Payers validate appropriateness of certain procedures "
             "in anticoagulated patients.",
         source_document="ICD-10-CM 2025; AHA Coding Clinic",
         data_confidence=0.94, rule_certainty="mandatory"),

    dict(code="M06.9", description="Rheumatoid arthritis, unspecified",
         value_tier="moderate", typical_setting="outpatient",
         settings=["professional","outpatient"], valid_as_primary_dx=False,
         audit_notes="High-value rheumatology code associated with expensive biologic therapies "
             "(TNF inhibitors, IL-6 inhibitors). Payers require step therapy documentation showing "
             "DMARD failure before approving biologics. Seronegative (M06.00) vs seropositive (M05.x) "
             "distinction important. HCC-relevant in Medicare Advantage.",
         source_document="ICD-10-CM 2025; CMS HCC Model V28; ACR RA Guidelines",
         data_confidence=0.92, rule_certainty="guideline"),

    dict(code="L40.0", description="Psoriasis vulgaris",
         value_tier="moderate", typical_setting="outpatient",
         settings=["professional","outpatient"], valid_as_primary_dx=False,
         audit_notes="Common dermatology code associated with high-cost biologic therapies "
             "(IL-17, IL-23, TNF inhibitors). Step therapy and body surface area (BSA) documentation "
             "are payer requirements for biologic PA. Psoriatic arthritis (L40.50–L40.59) has distinct "
             "codes and treatment pathways. Phototherapy (96900, 96910) frequency limits are payer-specific.",
         source_document="ICD-10-CM 2025; AAD Psoriasis Guidelines",
         data_confidence=0.91, rule_certainty="guideline"),

    dict(code="E11.65", description="Type 2 diabetes mellitus with hyperglycemia",
         value_tier="moderate", typical_setting="both",
         settings=["professional","outpatient","inpatient"], valid_as_primary_dx=False,
         audit_notes="More specific than E11.9; appropriate when hyperglycemia is documented. "
             "HCC-relevant — same HCC weight as E11.9 in V28 but better reflects clinical complexity. "
             "Insulin use requires Z79.4 as additional code. Inpatient hyperglycemia management is a "
             "quality metric; documentation of insulin protocol supports medical necessity.",
         source_document="ICD-10-CM 2025; CMS HCC Model V28; ADA Standards of Care",
         data_confidence=0.93, rule_certainty="mandatory"),

    dict(code="Z12.4", description="Encounter for screening for malignant neoplasm of cervix",
         value_tier="low", typical_setting="outpatient",
         settings=["professional","outpatient"], valid_as_primary_dx=False,
         audit_notes="Sex-specific preventive screening — immediately flagged if billed for male "
             "beneficiary. USPSTF: every 3 years (cytology alone) or 5 years (co-testing). Frequency "
             "limits strictly enforced. When abnormal findings lead to colposcopy (CPT 57454), the DX "
             "transitions from screening to diagnostic.",
         source_document="ICD-10-CM 2025; USPSTF Cervical Cancer Screening; CMS PFS",
         data_confidence=0.95, rule_certainty="mandatory"),

    # ── SNF ────────────────────────────────────────────────────────────────

    dict(code="U07.1", description="COVID-19",
         value_tier="high", typical_setting="both",
         settings=["snf","inpatient","outpatient","professional","home_health"],
         valid_as_primary_dx=True,
         audit_notes="Top SNF diagnosis at 9.33% of all SNF claims (Definitive HC Oct 2023). "
             "Requires confirmed positive test or provider documentation of confirmed COVID-19. "
             "Suspected/possible COVID uses Z20.822. Post-PHE, payers review for clinical documentation "
             "adequacy. Sequencing: U07.1 is principal when COVID causes pneumonia; when it causes sepsis, "
             "A41.xx is principal.",
         source_document="ICD-10-CM 2025; CMS COVID-19 Coding Guidelines; Definitive HC Oct 2023",
         data_confidence=0.96, rule_certainty="mandatory"),

    dict(code="F01.50", description="Vascular dementia, unspecified severity",
         value_tier="moderate", typical_setting="inpatient",
         settings=["snf","home_health"], valid_as_primary_dx=False,
         audit_notes="Common long-stay SNF diagnosis. FY2023 added severity specifiers (F01.50 "
             "unspecified, F01.51 mild, F01.52 moderate, F01.53 severe). MDS cognitive scores should "
             "reconcile with coded severity. HCC-relevant in Medicare Advantage — accurate dementia "
             "coding significantly affects RAF scores.",
         source_document="ICD-10-CM 2025; CMS MDS 3.0; CMS HCC Model V28",
         data_confidence=0.92, rule_certainty="guideline"),

    dict(code="F03.90", description="Unspecified dementia without behavioral disturbance, unspecified severity",
         value_tier="moderate", typical_setting="inpatient",
         settings=["snf","home_health"], valid_as_primary_dx=False,
         audit_notes="High-volume long-stay SNF and home health. When etiology is known (Alzheimer's "
             "G30.x, vascular F01.x, Lewy body G31.83), the specific type should be coded with F02.8x. "
             "F03.x is appropriate only when etiology is truly undetermined. Behavioral disturbance "
             "(F03.91x) requires documentation of aggressive or wandering behavior. MDS indicators "
             "should align with coded diagnosis.",
         source_document="ICD-10-CM 2025; CMS MDS 3.0; AHA Coding Clinic 4Q2019",
         data_confidence=0.91, rule_certainty="guideline"),

    dict(code="L89.90", description="Pressure ulcer of unspecified site, unspecified stage",
         value_tier="high", typical_setting="inpatient",
         settings=["snf","inpatient","home_health"], valid_as_primary_dx=False,
         audit_notes="HAC when not POA for inpatient — CMS does not pay higher DRG severity for "
             "pressure injuries acquired during the stay. Site and stage specificity (Stage I–IV, "
             "unstageable, deep tissue) are required when documented. SNF pressure ulcers are a CMS "
             "quality measure and survey trigger. Home health wound care claims require homebound "
             "criterion and skilled care necessity review.",
         source_document="ICD-10-CM 2025; CMS HAC List FY2025; NPUAP Staging Guidelines",
         data_confidence=0.95, rule_certainty="mandatory"),

    dict(code="R26.81", description="Unsteadiness on feet",
         value_tier="low", typical_setting="outpatient",
         settings=["snf","home_health","professional"], valid_as_primary_dx=False,
         audit_notes="Common SNF and home health functional status code; supports fall risk documentation "
             "and PT medical necessity. When underlying cause is identified (neuropathy, vestibular, "
             "Parkinson's), the specific condition should be principal with R26.81 as secondary. "
             "PT claims require documented functional limitations and measurable goals.",
         source_document="ICD-10-CM 2025; CMS SNF CoP; Medicare PT LCD",
         data_confidence=0.90, rule_certainty="heuristic"),

    dict(code="Z99.11", description="Dependence on respirator [ventilator] status",
         value_tier="high", typical_setting="inpatient",
         settings=["snf"], valid_as_primary_dx=False,
         audit_notes="Status code for ventilator-dependent SNF patients — high-cost PDPM case-mix "
             "category. CMS requires separate documentation of ventilator dependence for SNF PDPM "
             "grouping. Ventilator weaning is an active therapy goal; weaning trials must be documented. "
             "Billing ventilator management without concurrent respiratory therapy documentation is an "
             "audit flag.",
         source_document="ICD-10-CM 2025; CMS SNF PDPM; CMS SNF Vent Guidelines",
         data_confidence=0.93, rule_certainty="mandatory"),

    dict(code="E86.0", description="Dehydration",
         value_tier="low", typical_setting="both",
         settings=["snf","home_health","outpatient"], valid_as_primary_dx=False,
         audit_notes="Common SNF secondary; must be clinically documented with lab values (BUN/Cr ratio, "
             "serum osmolality) or clinical signs, not assumed. Dehydration combined with AKI (N17.9) "
             "or electrolyte abnormalities is a common inpatient admission trigger from SNF. Home health "
             "IV hydration requires specific physician orders and medical necessity documentation.",
         source_document="ICD-10-CM 2025; CMS SNF Coverage Criteria",
         data_confidence=0.90, rule_certainty="guideline"),

    dict(code="Z96.641", description="Presence of right artificial knee joint",
         value_tier="moderate", typical_setting="outpatient",
         settings=["snf","irf","outpatient"], valid_as_primary_dx=False,
         audit_notes="Post-TKA status code used in SNF and IRF post-acute admissions. IRF admission "
             "following total knee replacement qualifies under CMS 60% rule — Z96.641 supports the "
             "qualifying condition documentation. SNF vs IRF level of care decision for post-TKA "
             "patients is a frequent audit target. When prosthesis complication is present (T84.0x), "
             "that code takes precedence.",
         source_document="ICD-10-CM 2025; CMS IRF 60% Rule; CMS IRF PPS",
         data_confidence=0.93, rule_certainty="mandatory"),

    dict(code="Z96.651", description="Presence of right artificial hip joint",
         value_tier="moderate", typical_setting="inpatient",
         settings=["snf","irf"], valid_as_primary_dx=False,
         audit_notes="Post-THA status; major IRF and SNF post-acute admission driver. Hip replacement "
             "is a CMS 60% qualifying condition for IRF. Post-THA IRF vs SNF placement decisions are "
             "scrutinized for medical necessity of intensive therapy (3-hour rule). Dislocation risk "
             "in early post-op period supports IRF-level precaution documentation.",
         source_document="ICD-10-CM 2025; CMS IRF 60% Rule",
         data_confidence=0.93, rule_certainty="mandatory"),

    dict(code="Z74.01", description="Bed confinement status",
         value_tier="low", typical_setting="inpatient",
         settings=["snf","home_health"], valid_as_primary_dx=False,
         audit_notes="Functional status code supporting homebound criterion for home health and SNF "
             "level of care justification. Must be reconciled with physician certification of homebound "
             "status for home health. Overuse without corresponding functional assessment documentation "
             "is an audit flag. MDS and OASIS scores should align with this coded status.",
         source_document="ICD-10-CM 2025; CMS HH CoP; CMS OASIS Guidelines",
         data_confidence=0.88, rule_certainty="heuristic"),

    dict(code="K59.00", description="Constipation, unspecified",
         value_tier="low", typical_setting="outpatient",
         settings=["snf","home_health"], valid_as_primary_dx=False,
         audit_notes="Common SNF secondary in elderly with opioid use, immobility, or low oral intake. "
             "Chronic constipation (K59.04) and opioid-induced constipation (K59.09 + F11.x) have "
             "distinct codes when documented. Relevant as secondary for SNF nursing bowel management "
             "protocol documentation.",
         source_document="ICD-10-CM 2025",
         data_confidence=0.88, rule_certainty="heuristic"),

    # ── HOME HEALTH ────────────────────────────────────────────────────────

    dict(code="I69.351", description="Hemiplegia and hemiparesis following cerebral infarction affecting right dominant side",
         value_tier="high", typical_setting="inpatient",
         settings=["home_health","irf","snf"], valid_as_primary_dx=False,
         audit_notes="Sequela code for post-stroke functional deficits. Requires specificity for side "
             "and dominance. Used extensively in IRF and home health for stroke rehab claims. Functional "
             "deficit codes (I69.x) must be paired with documented therapy goals and measurable functional "
             "limitations. Sequela codes should NOT be used for acute stroke — I63.x is appropriate "
             "during the acute episode.",
         source_document="ICD-10-CM 2025; ICD-10-CM Guidelines I.C.9.d; CMS IRF PPS",
         data_confidence=0.93, rule_certainty="mandatory"),

    dict(code="M79.3", description="Panniculitis, unspecified",
         value_tier="low", typical_setting="outpatient",
         settings=["home_health","outpatient"], valid_as_primary_dx=False,
         audit_notes="Relatively low-volume; when used as primary home health DX should be supported "
             "by documented skilled nursing wound care. Specificity to lupus panniculitis (L93.2) or "
             "other specified type preferred. Home health wound care requires OASIS M1306/M1308 wound "
             "assessment. Subcutaneous tissue infections (L03.x) should be distinguished.",
         source_document="ICD-10-CM 2025; CMS OASIS Requirements",
         data_confidence=0.82, rule_certainty="heuristic"),

    dict(code="M16.11", description="Unilateral primary osteoarthritis, right hip",
         value_tier="moderate", typical_setting="outpatient",
         settings=["home_health","snf","irf"], valid_as_primary_dx=False,
         audit_notes="Post-hip arthroplasty home health and SNF driver. When hip replacement has "
             "occurred, Z96.651 (prosthesis presence) and aftercare codes (Z47.1) are more appropriate "
             "than continuing to code OA. Active OA coding post-arthroplasty without documentation of "
             "ongoing findings is a specificity flag. PT/OT goals require measurable outcomes.",
         source_document="ICD-10-CM 2025; CMS HH Coverage Criteria",
         data_confidence=0.91, rule_certainty="guideline"),

    dict(code="Z48.815", description="Encounter for surgical aftercare following surgery on the digestive system",
         value_tier="moderate", typical_setting="outpatient",
         settings=["home_health","outpatient"], valid_as_primary_dx=False,
         audit_notes="Aftercare code for post-surgical home health following GI surgery (colostomy, "
             "bowel resection, etc.). Must be paired with the condition that led to surgery and any "
             "current complications. Home health wound care for surgical incisions commonly associated. "
             "OASIS wound scores and visit frequency must be proportionate to wound complexity.",
         source_document="ICD-10-CM 2025; ICD-10-CM Guidelines I.C.21.c; CMS HH LCD",
         data_confidence=0.89, rule_certainty="guideline"),

    dict(code="E11.621", description="Type 2 diabetes mellitus with foot ulcer",
         value_tier="high", typical_setting="outpatient",
         settings=["home_health","outpatient","professional"], valid_as_primary_dx=False,
         audit_notes="High-value home health DX combining diabetes with active wound — drives skilled "
             "nursing visits for wound care and education. Additional code L97.4xx for specific foot "
             "ulcer location and severity required per ICD-10-CM guidelines. OASIS wound assessment "
             "must document ulcer characteristics. Debridement and wound care CPTs associated with "
             "this DX are high-audit targets for frequency and medical necessity.",
         source_document="ICD-10-CM 2025; ICD-10-CM Guidelines I.C.4.a; CMS HH LCD",
         data_confidence=0.94, rule_certainty="mandatory"),

    dict(code="Z47.1", description="Aftercare following joint replacement surgery",
         value_tier="moderate", typical_setting="outpatient",
         settings=["home_health","outpatient"], valid_as_primary_dx=False,
         audit_notes="Post-arthroplasty aftercare; requires additional code for joint replaced "
             "(Z96.641, Z96.651). Home health PT/OT must document measurable functional progress and "
             "homebound status. CMS has scrutinized home health claims following elective joint "
             "replacement for homebound criterion compliance — patients who underwent elective surgery "
             "and live with a caregiver may not meet homebound criteria.",
         source_document="ICD-10-CM 2025; CMS HH Coverage Criteria; OIG HH Audit Reports",
         data_confidence=0.93, rule_certainty="mandatory"),

    dict(code="I69.391", description="Other sequelae of cerebral infarction",
         value_tier="moderate", typical_setting="outpatient",
         settings=["home_health","irf"], valid_as_primary_dx=False,
         audit_notes="Catch-all sequela code for post-stroke deficits not captured by specific "
             "I69.3xx codes (dysphagia I69.391, aphasia I69.320, cognitive deficits I69.31x). "
             "Specific sequela codes should be used when documented. Home health speech therapy "
             "requires aphasia or dysphagia documentation with specific measurable goals.",
         source_document="ICD-10-CM 2025; ICD-10-CM Guidelines I.C.9.d",
         data_confidence=0.90, rule_certainty="guideline"),

    dict(code="J96.10", description="Chronic respiratory failure, unspecified whether with hypoxia or hypercapnia",
         value_tier="high", typical_setting="inpatient",
         settings=["home_health","snf"], valid_as_primary_dx=False,
         audit_notes="Supports home health oxygen therapy (E1390, E0431) and respiratory therapy. "
             "Home oxygen requires documented hypoxia (SpO2 ≤88% at rest or with exertion) via CMN. "
             "DMEPOS oxygen claims with J96.10 are independently subject to audit against CMN "
             "documentation. Home health skilled nursing for respiratory management must document "
             "specific interventions and patient response.",
         source_document="ICD-10-CM 2025; CMS LCD L33797 (Home Oxygen); CMS DMEPOS",
         data_confidence=0.92, rule_certainty="mandatory"),

    # ── IRF ────────────────────────────────────────────────────────────────

    dict(code="G20", description="Parkinson's disease",
         value_tier="high", typical_setting="both",
         settings=["irf","snf","home_health","outpatient"], valid_as_primary_dx=True,
         audit_notes="CMS 60% qualifying condition for IRF. Parkinson's with functional decline "
             "(falls, dysphagia, gait instability) supports IRF admission when intensive rehab potential "
             "is documented. HCC-relevant — significant RAF impact in Medicare Advantage. DBS (deep brain "
             "stimulation) implantation and programming are high-cost associated procedures. Home health "
             "PT for fall prevention and SNF for post-fall fracture are common pathways.",
         source_document="ICD-10-CM 2025; CMS IRF 60% Rule; CMS HCC Model V28",
         data_confidence=0.94, rule_certainty="mandatory"),

    dict(code="M05.79", description="Rheumatoid arthritis with rheumatoid factor of multiple sites without organ or systems involvement",
         value_tier="moderate", typical_setting="outpatient",
         settings=["irf","professional"], valid_as_primary_dx=False,
         audit_notes="Seropositive RA with significant joint involvement is a CMS 60% qualifying "
             "condition for IRF. IRF admission requires documented functional limitations requiring "
             "intensive inpatient rehabilitation, not just ongoing disease management. FIM admission "
             "and discharge scores required. Biologic therapy claims commonly associated in outpatient.",
         source_document="ICD-10-CM 2025; CMS IRF 60% Rule",
         data_confidence=0.90, rule_certainty="guideline"),

    dict(code="S32.001A", description="Wedge compression fracture of unspecified lumbar vertebra, initial encounter for closed fracture",
         value_tier="high", typical_setting="inpatient",
         settings=["irf","snf","inpatient"], valid_as_primary_dx=True,
         audit_notes="Vertebral fracture is a CMS 60% qualifying condition for IRF. 7th character "
             "specifies encounter type (A=initial, D=subsequent, G=delayed healing, K=nonunion, S=sequela) "
             "— wrong 7th character is a common error. Pathological fracture (M84.5x) vs traumatic "
             "requires documentation review. Vertebroplasty/kyphoplasty (CPT 22510–22515) medical "
             "necessity is a separate audit concern.",
         source_document="ICD-10-CM 2025; CMS IRF 60% Rule; CMS NCD 150.13",
         data_confidence=0.92, rule_certainty="mandatory"),

    dict(code="G45.9", description="Transient ischaemic attack, unspecified",
         value_tier="moderate", typical_setting="inpatient",
         settings=["irf","inpatient","outpatient"], valid_as_primary_dx=True,
         audit_notes="TIA does NOT qualify as a stroke for IRF admission — this is a common audit "
             "finding. IRF admission following TIA without residual neurological deficit is frequently "
             "denied. Code residual neurological deficit (I69.3xx) when present, not the TIA. When no "
             "residual deficit exists post-TIA, IRF level of care is generally not appropriate.",
         source_document="ICD-10-CM 2025; ICD-10-CM Guidelines I.C.9.d; CMS IRF Coverage Criteria",
         data_confidence=0.95, rule_certainty="mandatory"),

    dict(code="Q70.00", description="Fused fingers, unspecified fingers, unspecified hand",
         value_tier="low", typical_setting="inpatient",
         settings=["irf"], valid_as_primary_dx=False,
         audit_notes="Congenital condition occasionally on IRF claims for post-surgical hand rehab. "
             "IRF admission requires significant functional limitation requiring intensive inpatient "
             "rehabilitation. Low-volume; data confidence reflects limited claims prevalence.",
         source_document="ICD-10-CM 2025; CMS IRF Coverage Criteria",
         data_confidence=0.75, rule_certainty="heuristic"),

    dict(code="G82.50", description="Quadriplegia, unspecified",
         value_tier="high", typical_setting="inpatient",
         settings=["irf","snf"], valid_as_primary_dx=True,
         audit_notes="SCI with quadriplegia/paraplegia is a CMS 60% qualifying condition for IRF. "
             "Completeness and level require specificity when documented (G82.21–G82.54). FIM scores "
             "at IRF admission must reflect deficits consistent with quadriplegia. Long-term SNF "
             "placement for ventilator-dependent quadriplegic patients has its own high-complexity "
             "PDPM category.",
         source_document="ICD-10-CM 2025; CMS IRF 60% Rule; ASIA Classification",
         data_confidence=0.93, rule_certainty="mandatory"),

    dict(code="I67.9", description="Cerebrovascular disease, unspecified",
         value_tier="moderate", typical_setting="inpatient",
         settings=["irf","inpatient"], valid_as_primary_dx=True,
         audit_notes="Frequently overused when specific cerebrovascular codes are available (I63.x "
             "infarction, I61.x hemorrhage, I67.1 cerebral aneurysm). I67.9 when specific stroke type "
             "is documented is a coding specificity and potential upcoding flag. CMS auditors scrutinize "
             "IRF claims with I67.9 as PDX — specific stroke codes with documented functional deficits "
             "are required to support IRF level of care.",
         source_document="ICD-10-CM 2025; ICD-10-CM Guidelines I.C.9",
         data_confidence=0.91, rule_certainty="guideline"),

    # ── SLEEP IN-LAB ──────────────────────────────────────────────────────

    dict(code="G47.33", description="Obstructive sleep apnea (adult)(pediatric)",
         value_tier="high", typical_setting="outpatient",
         settings=["sleep_inlab","sleep_home","professional","outpatient"],
         valid_as_primary_dx=True,
         audit_notes="Primary DX for PSG (95810/95811) and HST (95806/95800). AHI from sleep study "
             "must support OSA; G47.33 is unspecified severity — clinical documentation should reflect "
             "AHI severity for medical necessity. CPAP equipment (E0601) and supplies require documented "
             "4-hour compliance. Payers audit CPAP resupply against compliance download data.",
         source_document="ICD-10-CM 2025; CMS LCD L33718; CMS DMEPOS CPAP",
         data_confidence=0.97, rule_certainty="mandatory"),

    dict(code="G47.31", description="Primary central sleep apnea",
         value_tier="high", typical_setting="outpatient",
         settings=["sleep_inlab"], valid_as_primary_dx=True,
         audit_notes="Distinct treatment implications — ASV rather than CPAP, with specific CMS coverage "
             "criteria. CMS restricts ASV for patients with systolic heart failure and predominant central "
             "sleep apnea (contraindicated per SERVE-HF). Treatment-emergent central apnea (G47.37) "
             "develops after CPAP initiation and has its own coding and coverage pathway.",
         source_document="ICD-10-CM 2025; CMS LCD L33718; CMS ASV Coverage Policy",
         data_confidence=0.93, rule_certainty="mandatory"),

    dict(code="G47.37", description="Central sleep apnea in conditions classified elsewhere",
         value_tier="moderate", typical_setting="outpatient",
         settings=["sleep_inlab"], valid_as_primary_dx=False,
         audit_notes="Treatment-emergent central apnea (TECA / complex sleep apnea) — develops after "
             "CPAP initiation. Requires in-lab titration study (95811) for CPAP-to-ASV upgrade; HST "
             "insufficient. Payers require documentation of CPAP trial failure and in-lab TECA "
             "confirmation before approving ASV. Underlying condition must also be coded.",
         source_document="ICD-10-CM 2025; CMS LCD L33718; AASM Treatment-Emergent CSA Guidelines",
         data_confidence=0.90, rule_certainty="guideline"),

    dict(code="G47.411", description="Narcolepsy with cataplexy",
         value_tier="high", typical_setting="outpatient",
         settings=["sleep_inlab"], valid_as_primary_dx=True,
         audit_notes="Requires MSLT (CPT 95805) following overnight PSG — mean sleep latency ≤8 min "
             "and ≥2 SOREMPs. High-cost medications (sodium oxybate/Xyrem, pitolisant/Wakix) require "
             "PA with confirmed PSG + MSLT results. Cataplexy documentation (sudden muscle weakness "
             "triggered by emotion) distinguishes G47.411 from G47.419 (without cataplexy).",
         source_document="ICD-10-CM 2025; AASM Narcolepsy Criteria; CMS LCD L34028",
         data_confidence=0.93, rule_certainty="mandatory"),

    dict(code="G47.52", description="REM sleep behavior disorder",
         value_tier="moderate", typical_setting="outpatient",
         settings=["sleep_inlab"], valid_as_primary_dx=True,
         audit_notes="Requires in-lab PSG with full video monitoring and EMG channels. HST is not "
             "appropriate for RBD evaluation. Clinical significance: RBD is strongly associated with "
             "prodromal synucleinopathy (Parkinson's, DLB, MSA). Documentation of dream enactment "
             "behavior and PSG findings (REM without atonia) are both required.",
         source_document="ICD-10-CM 2025; AASM ICSD-3; CMS LCD for In-Lab PSG",
         data_confidence=0.90, rule_certainty="guideline"),

    dict(code="G47.61", description="Periodic limb movement disorder",
         value_tier="low", typical_setting="outpatient",
         settings=["sleep_inlab","professional"], valid_as_primary_dx=False,
         audit_notes="PLMD requires PSG with leg EMG; PLMS index ≥15/hour in adults with clinical "
             "sleep disturbance. Distinguish from RLS (G25.81) — RLS is waking sensory, PLMD is "
             "nocturnal motor. Payers may not reimburse PSG solely for PLMD without concurrent OSA "
             "or other sleep disorder.",
         source_document="ICD-10-CM 2025; AASM ICSD-3",
         data_confidence=0.88, rule_certainty="guideline"),

    dict(code="G25.81", description="Restless legs syndrome",
         value_tier="low", typical_setting="outpatient",
         settings=["sleep_inlab","professional"], valid_as_primary_dx=False,
         audit_notes="Clinical diagnosis — does not require PSG per AASM criteria. PSG ordered for "
             "RLS alone may be denied as not medically necessary. Iron deficiency (D50.9) and renal "
             "failure (N18.x) should be coded as secondary contributing factors when documented.",
         source_document="ICD-10-CM 2025; AASM RLS Criteria; CMS LCD L34028",
         data_confidence=0.91, rule_certainty="guideline"),

    dict(code="G47.50", description="Parasomnia, unspecified",
         value_tier="low", typical_setting="outpatient",
         settings=["sleep_inlab"], valid_as_primary_dx=False,
         audit_notes="Specific parasomnia codes (G47.51 confusional arousals, G47.52 RBD, G47.59 "
             "other) should be used when documented. Video-PSG is standard for parasomnia evaluation. "
             "Payers audit PSG for parasomnia when medical necessity is unclear — behavioral safety "
             "risk or violent behaviors must be documented to support in-lab testing.",
         source_document="ICD-10-CM 2025; AASM ICSD-3",
         data_confidence=0.85, rule_certainty="heuristic"),

    # ── HOME SLEEP TEST ────────────────────────────────────────────────────

    dict(code="G47.30", description="Sleep apnea, unspecified",
         value_tier="moderate", typical_setting="outpatient",
         settings=["sleep_home","sleep_inlab"], valid_as_primary_dx=True,
         audit_notes="Use G47.30 only when sleep apnea type cannot be determined prior to testing. "
             "Post-study, code specific type (G47.33, G47.31). HST (CPT 95806, 95800) is appropriate "
             "for suspected uncomplicated OSA without significant comorbidities per CMS LCD. G47.30 "
             "persisting after a completed study is a coding specificity flag.",
         source_document="ICD-10-CM 2025; CMS LCD L33718; AASM HST Guidelines",
         data_confidence=0.92, rule_certainty="guideline"),

    dict(code="R06.83", description="Snoring",
         value_tier="low", typical_setting="outpatient",
         settings=["sleep_home","sleep_inlab","professional"], valid_as_primary_dx=False,
         audit_notes="Snoring alone is insufficient to support HST or PSG in most payer LCDs. "
             "Witnessed apnea, excessive daytime sleepiness (R53.83), or morning headache must accompany "
             "it. R06.83 as sole DX on a sleep study claim will likely deny. Mandibular advancement "
             "device (E0486) requires confirmed OSA diagnosis, not just snoring.",
         source_document="ICD-10-CM 2025; CMS LCD L33718",
         data_confidence=0.93, rule_certainty="mandatory"),

    dict(code="R53.83", description="Other fatigue",
         value_tier="low", typical_setting="outpatient",
         settings=["sleep_home","sleep_inlab","professional"], valid_as_primary_dx=False,
         audit_notes="Key supporting symptom for sleep study medical necessity. LCD criteria for HST "
             "typically require documented EDS, witnessed apneas, or Epworth Sleepiness Scale ≥10. "
             "As standalone primary diagnosis, R53.83 is insufficiently specific for sleep study "
             "authorization. G47.10–G47.19 (hypersomnia) should be used when hypersomnia is established.",
         source_document="ICD-10-CM 2025; CMS LCD L33718; Epworth Sleepiness Scale",
         data_confidence=0.91, rule_certainty="guideline"),

    dict(code="E66.01", description="Morbid (severe) obesity due to excess calories",
         value_tier="moderate", typical_setting="outpatient",
         settings=["sleep_home","sleep_inlab","professional","outpatient"], valid_as_primary_dx=False,
         audit_notes="BMI ≥40 is a strong OSA risk factor supporting HST medical necessity as "
             "secondary DX. Z68.4x BMI code required additionally. Morbid obesity may require "
             "in-lab PSG rather than HST per some payer LCDs due to positional testing limitations. "
             "Bariatric surgery (CPT 43775–43845) PA commonly involves sleep apnea documentation.",
         source_document="ICD-10-CM 2025; CMS LCD L33718; ASMBS Bariatric Guidelines",
         data_confidence=0.93, rule_certainty="guideline"),

    dict(code="I50.32", description="Chronic diastolic (congestive) heart failure",
         value_tier="high", typical_setting="both",
         settings=["sleep_home","sleep_inlab","inpatient","home_health"], valid_as_primary_dx=False,
         audit_notes="HF with reduced EF (HFrEF) combined with central sleep apnea is an ASV "
             "CONTRAINDICATION per SERVE-HF trial — ASV is not covered by CMS for this combination. "
             "When I50.32 (or I50.22 systolic) appears with G47.31 (central SA) and an ASV order, "
             "this is a critical coverage and patient safety flag. HST generally insufficient for "
             "CHF patients with suspected sleep apnea — in-lab PSG preferred per most LCDs.",
         source_document="ICD-10-CM 2025; CMS LCD L33718; SERVE-HF Trial; AHA HF Guidelines",
         data_confidence=0.95, rule_certainty="mandatory"),

    dict(code="J44.9", description="Chronic obstructive pulmonary disease, unspecified",
         value_tier="moderate", typical_setting="both",
         settings=["sleep_home","sleep_inlab","inpatient","snf","home_health"],
         valid_as_primary_dx=False,
         audit_notes="Overlap syndrome (COPD + OSA) requires in-lab PSG per most payer LCDs; HST "
             "is generally not appropriate with significant COPD due to baseline hypoxemia. J44.9 on "
             "an HST claim may trigger a clinical appropriateness review. BiPAP ST (E0471) or ASV "
             "may be required for COPD-OSA overlap rather than standard CPAP.",
         source_document="ICD-10-CM 2025; CMS LCD L33718; AASM HST Contraindications",
         data_confidence=0.94, rule_certainty="mandatory"),

    dict(code="G47.19", description="Other hypersomnia",
         value_tier="low", typical_setting="outpatient",
         settings=["sleep_home","sleep_inlab"], valid_as_primary_dx=False,
         audit_notes="Hypersomnia of central origin requires in-lab MSLT (CPT 95805), not HST. "
             "Idiopathic hypersomnia (G47.11) requires two consecutive nights of PSG plus MSLT. "
             "HST will be denied when hypersomnia is the sole indication without concurrent OSA "
             "suspicion.",
         source_document="ICD-10-CM 2025; AASM ICSD-3; CMS LCD L34028",
         data_confidence=0.89, rule_certainty="guideline"),

    dict(code="R00.1", description="Bradycardia, unspecified",
         value_tier="moderate", typical_setting="outpatient",
         settings=["sleep_home","sleep_inlab"], valid_as_primary_dx=False,
         audit_notes="Nocturnal bradycardia is a known OSA comorbidity — supporting context for "
             "sleep study medical necessity. However, cardiac arrhythmia may make HST inadequate per "
             "some LCDs, directing to in-lab PSG with cardiac monitoring. R00.1 on an HST claim may "
             "trigger clinical appropriateness review. If bradycardia is the primary concern, Holter "
             "monitor is more appropriate than HST.",
         source_document="ICD-10-CM 2025; CMS LCD L33718; ACC/AHA Bradycardia Guidelines",
         data_confidence=0.87, rule_certainty="heuristic"),

    # ── NEPHROLOGY & KIDNEY DISEASE ────────────────────────────────────────

    dict(code="N18.1", description="Chronic kidney disease, stage 1",
         value_tier="high", typical_setting="both",
         settings=["inpatient","outpatient","professional","home_health","snf"],
         valid_as_primary_dx=True,
         audit_notes="CKD Stage 1 (GFR ≥90). Requires documentation of kidney disease or albuminuria. "
             "Often missed because serum creatinine is normal; eGFR-based staging is critical. "
             "HCC-relevant (HCC 332). Drives monitoring frequency and medication choices. N18.3 "
             "(Stage 3) is highest-volume; Stage 1 is usually asymptomatic and discovered incidentally.",
         source_document="ICD-10-CM 2025; KDIGO Clinical Practice Guidelines; CMS HCC Model V28",
         data_confidence=0.95, rule_certainty="mandatory"),

    dict(code="N18.2", description="Chronic kidney disease, stage 2",
         value_tier="high", typical_setting="both",
         settings=["inpatient","outpatient","professional","home_health","snf"],
         valid_as_primary_dx=True,
         audit_notes="CKD Stage 2 (GFR 60–89). Mild reduction in kidney function; requires albuminuria "
             "or other kidney damage evidence for CKD diagnosis. HCC-relevant (HCC 332). Associated codes: "
             "N18.30 (Stage 3a), E11.21 (Type 2 diabetes with nephropathy), I12.9 (hypertensive kidney disease). "
             "ACE inhibitors/ARBs are standard of care when documented.",
         source_document="ICD-10-CM 2025; KDIGO Guidelines; USRDS Annual Report",
         data_confidence=0.95, rule_certainty="mandatory"),

    dict(code="N18.30", description="Chronic kidney disease, stage 3a",
         value_tier="high", typical_setting="both",
         settings=["inpatient","outpatient","professional","home_health","snf","irf"],
         valid_as_primary_dx=True,
         audit_notes="CKD Stage 3a (GFR 45–59). Moderate reduction in GFR — highest-volume CKD stage. "
             "Triggers close monitoring, medication adjustments (renally dose all drugs), and discussion "
             "of vascular access planning when progressing. N18.3 unspecified is outdated; always specify "
             "3a vs 3b. HCC 332. Nephrology referral at this stage prevents progression to ESRD. "
             "Anemia (D64.9) commonly coexists and may require ESA.",
         source_document="ICD-10-CM 2025; KDIGO; CMS NCD for ESRD",
         data_confidence=0.96, rule_certainty="mandatory"),

    dict(code="N18.31", description="Chronic kidney disease, stage 3a",
         value_tier="high", typical_setting="both",
         settings=["inpatient","outpatient","professional","home_health","snf","irf"],
         valid_as_primary_dx=True,
         audit_notes="CKD Stage 3a with 5th character specificity — synonym for N18.30. Some coders use "
             "both interchangeably; ICD-10-CM 2025 has consolidated to N18.30/N18.31. High-volume outpatient; "
             "dialysis preparation often begins here. Medication reconciliation essential to avoid nephrotoxic "
             "agents (NSAIDs, contrast). HCC 332 applies.",
         source_document="ICD-10-CM 2025",
         data_confidence=0.95, rule_certainty="mandatory"),

    dict(code="N18.32", description="Chronic kidney disease, stage 3b",
         value_tier="high", typical_setting="both",
         settings=["inpatient","outpatient","professional","home_health","snf","irf"],
         valid_as_primary_dx=True,
         audit_notes="CKD Stage 3b (GFR 30–44). More severe decline; vascular access planning and "
             "nephrology co-management routine. Medication renalization intensifies. Phosphate binders, "
             "calcium supplements, vitamin D analogs typically initiated. Education for dialysis modality "
             "choice (in-center vs home) common. N18.3 unspecified is now deprecated in favor of 3a/3b. "
             "HCC 332. Close monitoring of potassium, phosphorus, calcium.",
         source_document="ICD-10-CM 2025; KDIGO; USRDS",
         data_confidence=0.96, rule_certainty="mandatory"),

    dict(code="N18.4", description="Chronic kidney disease, stage 4",
         value_tier="high", typical_setting="both",
         settings=["inpatient","outpatient","professional","home_health","snf","irf"],
         valid_as_primary_dx=True,
         audit_notes="CKD Stage 4 (GFR 15–29). Severely reduced kidney function. Vascular access creation "
             "(AV fistula CPT 36821, graft 36825) becomes urgent. Dialysis education and initiation planning "
             "in progress. Comorbidities (diabetes, hypertension, anemia) management critical. Nephrology should "
             "be primary coordinator. HCC 332. Home health for education, monitoring. Multiple drug interactions "
             "and renalization rules apply. Electrolyte abnormalities common.",
         source_document="ICD-10-CM 2025; CMS NCD L24899; KDIGO",
         data_confidence=0.97, rule_certainty="mandatory"),

    dict(code="N18.5", description="Chronic kidney disease, stage 5",
         value_tier="high", typical_setting="both",
         settings=["inpatient","outpatient","professional","home_health","snf","irf"],
         valid_as_primary_dx=True,
         audit_notes="CKD Stage 5 (GFR <15). End-stage kidney disease; dialysis or transplant imminent. "
             "N18.6 (ESRD) is the formal diagnostic term for insurance/CMS purposes, but N18.5 may appear "
             "before dialysis initiation or on claims where ESRD status is still establishing. CPT 90935–90947 "
             "(hemodialysis) or 90989–90997 (peritoneal dialysis) codes required. Home health involvement routine. "
             "Transplant coordination if eligible. HCC 332. Multiple comorbidities (anemia, bone disease, "
             "hypertension, cardiovascular) require active management.",
         source_document="ICD-10-CM 2025; CMS NCD L24899; KDIGO; USRDS Core Curriculum",
         data_confidence=0.98, rule_certainty="mandatory"),

    dict(code="N18.6", description="End-stage renal disease",
         value_tier="high", typical_setting="both",
         settings=["inpatient","outpatient","professional","home_health","snf","irf"],
         valid_as_primary_dx=True,
         audit_notes="ESRD — formal diagnosis for Stage 5 CKD on dialysis or post-transplant. Triggers "
             "CMS payment models (ESRD PPS for in-center hemodialysis; home dialysis alternative payment model). "
             "Code BOTH N18.6 and the specific dialysis procedure (CPT 90935, 90989, etc.). Transplant status "
             "coded separately (Z94.0). Anemia (D64.9), mineral bone disease, hypertension, cardiovascular "
             "disease nearly universal. Multiple comorbidities drive HCC coding (HCC 332 + others). Nephrology "
             "visits (90xxx codes) monthly minimum. CPM/SNF often required for vascular access management.",
         source_document="ICD-10-CM 2025; CMS ESRD Payment System; USRDS",
         data_confidence=0.99, rule_certainty="mandatory"),

    dict(code="N18.9", description="Chronic kidney disease, unspecified",
         value_tier="moderate", typical_setting="both",
         settings=["inpatient","outpatient","professional"],
         valid_as_primary_dx=True,
         audit_notes="Non-specific; N18.30/N18.31/N18.32/N18.4/N18.5/N18.6 strongly preferred when stage "
             "can be determined from labs (eGFR). N18.9 used when stage is clinically unclear or documentation "
             "is insufficient. Auditors often query N18.9 for lack of specificity. If GFR labs are available, "
             "stage assignment is expected. HCC 332 still applies but represents lower-acuity documentation.",
         source_document="ICD-10-CM 2025; AHA Coding Clinic",
         data_confidence=0.90, rule_certainty="guideline"),

    dict(code="N17.0", description="Acute kidney injury with RIFLE: Risk stage",
         value_tier="high", typical_setting="inpatient",
         settings=["inpatient"], valid_as_primary_dx=True,
         audit_notes="Acute Kidney Injury (AKI) RIFLE staging. N17.0 (Risk), N17.1 (Injury), N17.2 (Failure). "
             "Replaces older N17.1–N17.3 classifications. Risk stage: serum creatinine increase 1.5–1.9× baseline "
             "or urine output 0.5–0.9 mL/kg/hr. Dialysis not yet required. Requires documentation of baseline "
             "creatinine. Common post-surgical or post-contrast exposure complication. DRG impact significant.",
         source_document="ICD-10-CM 2025; Acute Kidney Injury Network (AKIN)",
         data_confidence=0.94, rule_certainty="mandatory"),

    dict(code="N17.1", description="Acute kidney injury with RIFLE: Injury stage",
         value_tier="high", typical_setting="inpatient",
         settings=["inpatient"], valid_as_primary_dx=True,
         audit_notes="AKI Injury stage: serum creatinine increase 2.0–2.9× baseline or urine output <0.5 "
             "mL/kg/hr for 8–16 hrs. More severe than Risk; may require dialysis initiation. Common in sepsis, "
             "cardiorenal syndrome, nephrotoxic drug exposure. DRG weight higher than Risk. Requires documentation "
             "of precipitating event and baseline kidney function. Post-operative AKI is common — validate causality "
             "in surgery claims.",
         source_document="ICD-10-CM 2025; AKIN Guidelines; KDIGO AKI Staging",
         data_confidence=0.95, rule_certainty="mandatory"),

    dict(code="N17.2", description="Acute kidney injury with RIFLE: Failure stage",
         value_tier="high", typical_setting="inpatient",
         settings=["inpatient","icu"], valid_as_primary_dx=True,
         audit_notes="AKI Failure stage (most severe): serum creatinine increase ≥3× baseline or absolute "
             "increase ≥4 mg/dL, or anuria ≥12 hrs. Dialysis almost always required. High mortality. Often "
             "associated with sepsis (A41.9), cardiogenic shock (R57.0), or multi-organ failure. ICU admission "
             "typical. DRG 684–686. Post-renal and intrinsic renal causes both common. If dialysis initiated, "
             "code CPT 90935 or 90989 per modality. Often leads to chronic kidney disease.",
         source_document="ICD-10-CM 2025; KDIGO AKI Guidelines",
         data_confidence=0.97, rule_certainty="mandatory"),

    dict(code="N17.9", description="Acute kidney injury, unspecified",
         value_tier="high", typical_setting="inpatient",
         settings=["inpatient","icu"], valid_as_primary_dx=True,
         audit_notes="AKI stage not specified or clinically unclear. Prefer N17.0/N17.1/N17.2 when staging "
             "criteria and creatinine kinetics are documented. N17.9 is non-specific but acceptable for initial "
             "presentation before workup complete. Comorbidity with CKD (N18.x) is common — both should be coded "
             "when documented (AKI on CKD). Dialysis initiation (if applicable) coded separately. May progress to "
             "chronic disease requiring transplant consideration.",
         source_document="ICD-10-CM 2025; KDIGO",
         data_confidence=0.91, rule_certainty="guideline"),

    dict(code="N00.9", description="Acute glomerulonephritis, unspecified",
         value_tier="high", typical_setting="inpatient",
         settings=["inpatient","outpatient"], valid_as_primary_dx=True,
         audit_notes="Acute nephritic syndrome with or without hematuria. Presents with hematuria, "
             "hypertension, edema, azotemia. Post-infectious (strep throat) common. Requires kidney biopsy "
             "for definitive diagnosis. N00–N08 are glomerulonephritis variants (IgA, membranoproliferative, "
             "proliferative, etc.). Immunosuppressive therapy may be indicated. Renal function recovery varies "
             "by etiology. Often progresses to chronic glomerulonephritis (N03.x) if not resolved.",
         source_document="ICD-10-CM 2025; AKF Nephrology Guidelines",
         data_confidence=0.92, rule_certainty="guideline"),

    dict(code="N01.9", description="Rapidly progressive glomerulonephritis, unspecified",
         value_tier="high", typical_setting="inpatient",
         settings=["inpatient"], valid_as_primary_dx=True,
         audit_notes="RPGN: Rapid progression to kidney failure over days to weeks, often with crescent "
             "formation on biopsy. Includes ANCA-associated vasculitis, anti-GBM disease. Medical emergency; "
             "requires urgent immunosuppression (plasmapheresis, corticosteroids, rituximab). ICU admission common. "
             "High risk of ESRD if not treated promptly. Dialysis initiation likely. Kidney biopsy essential for "
             "subtype and prognosis.",
         source_document="ICD-10-CM 2025; KDIGO RPGN Guidelines",
         data_confidence=0.93, rule_certainty="mandatory"),

    dict(code="N03.9", description="Chronic glomerulonephritis, unspecified",
         value_tier="high", typical_setting="both",
         settings=["inpatient","outpatient","professional","home_health","snf"],
         valid_as_primary_dx=True,
         audit_notes="Chronic nephritic syndrome (hematuria ± proteinuria without nephrotic-range protein). "
             "Often residual from prior acute glomerulonephritis or primary glomerulonephritis (N03.1–N03.7 "
             "specify membrane type). Progressive to CKD over years/decades. Proteinuria measurement (urinalysis "
             "CPT 81000) and renal function monitoring routine. ACE-I/ARB for proteinuria reduction standard. "
             "Secondary causes (SLE, hepatitis C) should be ruled out. Nephrology co-management typical.",
         source_document="ICD-10-CM 2025; KDIGO Glomerulonephritis Management",
         data_confidence=0.91, rule_certainty="guideline"),

    dict(code="N04.9", description="Nephrotic syndrome, unspecified",
         value_tier="high", typical_setting="both",
         settings=["inpatient","outpatient","professional","home_health","snf"],
         valid_as_primary_dx=True,
         audit_notes="Nephrotic syndrome: proteinuria ≥3.5 g/day, hypoalbuminemia, hyperlipidemia, edema. "
             "Causes: minimal change disease (40%, children), focal segmental sclerosis (35%), membranoproliferative "
             "(15%), other (10%). N04.0–N04.8 specify histologic type when documented. High risk for thromboembolic "
             "complications. Diuretics, NSAIDs, albumin infusion, corticosteroids/immunosuppressive agents per etiology. "
             "Close monitoring of renal function, electrolytes, lipids. May progress to CKD/ESRD.",
         source_document="ICD-10-CM 2025; KDIGO Nephrotic Syndrome Guidelines",
         data_confidence=0.93, rule_certainty="mandatory"),

    dict(code="E11.21", description="Type 2 diabetes mellitus with diabetic nephropathy",
         value_tier="high", typical_setting="both",
         settings=["inpatient","outpatient","professional","home_health","snf"],
         valid_as_primary_dx=True,
         audit_notes="Diabetic kidney disease — Type 2 diabetes with albuminuria and/or reduced eGFR. "
             "Leading cause of ESRD in US; ~40% of Type 2 diabetics develop nephropathy. Requires concurrent "
             "N-code (N18.1–N18.6, or N04.x if nephrotic-range proteinuria). HCC-relevant (HCC 19, 332). "
             "ACE-I/ARB (therapeutic drug monitoring CPT 80200s) mandated for reduction of proteinuria. "
             "Glucose control (HbA1c CPT 83036) and blood pressure targets critical. SGLT2i increasingly used. "
             "Ophthalmology screening for retinopathy required.",
         source_document="ICD-10-CM 2025; ADA Standards; CMS HCC Model V28",
         data_confidence=0.97, rule_certainty="mandatory"),

    dict(code="E11.22", description="Type 2 diabetes mellitus with diabetic chronic kidney disease",
         value_tier="high", typical_setting="both",
         settings=["inpatient","outpatient","professional","home_health","snf"],
         valid_as_primary_dx=True,
         audit_notes="Type 2 diabetes with established CKD (stages 1-5 or ESRD). Distinction from E11.21 "
             "(nephropathy): E11.22 is used when CKD stage is documented per N18.x coding. Both codes emphasize "
             "kidney dysfunction severity. Requires concurrent N-code (N18.1–N18.6) specifying CKD stage. "
             "HCC-relevant (HCC 19, 332). ACE-I/ARB essential; renalization of all medications required based "
             "on eGFR. Glucose control (HbA1c target <7% per KDIGO) and BP management (<120 mmHg systolic per "
             "ACCORD BP trial) critical. SGLT2i and GLP-1 RAs increasingly evidence-based. Nephrology referral "
             "when eGFR <30. Retinopathy, neuropathy, cardiovascular screening routine.",
         source_document="ICD-10-CM 2025; KDIGO Diabetes Management; ADA Standards",
         data_confidence=0.96, rule_certainty="mandatory"),

    dict(code="E10.21", description="Type 1 diabetes mellitus with diabetic nephropathy",
         value_tier="high", typical_setting="both",
         settings=["inpatient","outpatient","professional","home_health","snf"],
         valid_as_primary_dx=True,
         audit_notes="Type 1 diabetes with kidney disease. ~30–40% develop nephropathy over 20–40 years. "
             "Almost universally requires N-code (N18.x, N04.x, or specific GN type). ACE-I/ARB essential. "
             "Strict glycemic control (target HbA1c <7%) strongly associated with nephropathy prevention. "
             "Retinopathy screening routine (dilated retinal exam 92012). Comorbid HTN almost universal; "
             "antihypertensive choice driven by albuminuria. Often leads to ESRD requiring dialysis/transplant. "
             "HCC-relevant. Transition of care to endocrinology and nephrology essential.",
         source_document="ICD-10-CM 2025; ADA Standards; KDIGO",
         data_confidence=0.96, rule_certainty="mandatory"),

    dict(code="I12.0", description="Hypertensive chronic kidney disease with stage 1 through 4 or unspecified CKD",
         value_tier="high", typical_setting="both",
         settings=["inpatient","outpatient","professional","home_health","snf"],
         valid_as_primary_dx=True,
         audit_notes="Hypertensive kidney disease (I12.x) is a combination code: hypertension + CKD. "
             "I12.0 is used with N18.1–N18.4 (or unspecified N18.9). I12.9 is reserved for Stage 5 CKD/ESRD "
             "(N18.5, N18.6). When both I10 (HTN) and N18.x (CKD) are documented, I12.x is the combination "
             "code and I10 is NOT coded separately per ICD-10-CM guidelines. HCC-relevant (HCC 332). "
             "ACE-I/ARB/CCB standard therapy; renin inhibitors if ARNI not tolerated. Sodium restriction. "
             "Regular renal function monitoring essential.",
         source_document="ICD-10-CM 2025; AHA Coding Clinic; KDIGO HTN/CKD Management",
         data_confidence=0.96, rule_certainty="mandatory"),

    dict(code="I12.9", description="Hypertensive chronic kidney disease with stage 5 chronic kidney disease or end stage renal disease",
         value_tier="high", typical_setting="both",
         settings=["inpatient","outpatient","professional","home_health","snf","irf"],
         valid_as_primary_dx=True,
         audit_notes="Hypertensive kidney disease with ESRD (N18.5, N18.6, or dialysis). I12.9 is the "
             "combination code for I10 + ESRD; I10 is NOT coded separately. Almost all ESRD patients have "
             "hypertension requiring antihypertensive adjustment in dialysis setting. Fluid/electrolyte/volume "
             "management intensive. Code BOTH I12.9 and the dialysis CPT (90935, 90989, etc.). Nephrology and "
             "cardiology co-management. Transplant candidacy evaluation ongoing. HCC-relevant (HCC 332).",
         source_document="ICD-10-CM 2025; CMS ESRD Payment System; KDIGO",
         data_confidence=0.98, rule_certainty="mandatory"),

    dict(code="N10", description="Acute pyelonephritis",
         value_tier="moderate", typical_setting="inpatient",
         settings=["inpatient","ed","outpatient"], valid_as_primary_dx=True,
         audit_notes="Acute bacterial infection of kidney/upper urinary tract. Presents with fever, "
             "costovertebral angle tenderness, dysuria, pyuria. Requires urine culture (87086) and broad-spectrum "
             "antibiotics initially. Most common organisms: E. coli (80%), Klebsiella, Proteus. Imaging (renal "
             "ultrasound CPT 76705 or CT abdomen 74176) when obstruction/abscess suspected. Uncomplicated pyelonephritis "
             "typically outpatient-appropriate; sepsis or pregnancy drives inpatient care. Post-treatment urinalysis "
             "to confirm clearance.",
         source_document="ICD-10-CM 2025; IDSA UTI Guidelines",
         data_confidence=0.94, rule_certainty="guideline"),

    dict(code="N11.9", description="Chronic pyelonephritis, unspecified",
         value_tier="moderate", typical_setting="outpatient",
         settings=["outpatient","professional","home_health","snf"],
         valid_as_primary_dx=True,
         audit_notes="Chronic kidney infection, usually from recurrent/persistent UTI or structural "
             "abnormality (obstruction, reflux, polycystic kidney disease). May present without acute symptoms. "
             "Renal scarring common; progressive to CKD over time. Underlying cause (e.g., N13.7 vesicoureteral "
             "reflux) should be identified. Prophylactic antibiotics sometimes used if frequent infections. "
             "Urology/nephrology referral often appropriate. Monitor renal function closely.",
         source_document="ICD-10-CM 2025; KDIGO UTI/Pyelonephritis Management",
         data_confidence=0.91, rule_certainty="guideline"),

    dict(code="N13.9", description="Obstructive and reflux uropathy, unspecified",
         value_tier="moderate", typical_setting="both",
         settings=["inpatient","outpatient","professional","home_health","snf"],
         valid_as_primary_dx=True,
         audit_notes="Urinary tract obstruction (kidney stone, tumor, stricture) or vesicoureteral reflux. "
             "N13.0–N13.8 specify type (reflux, calculus, fibrosis, stenosis, etc.). Presents with flank pain, "
             "hematuria, or asymptomatic hydroureter/hydronephrosis on imaging. Imaging essential (ultrasound "
             "CPT 76705, CT 74176). Complications: pyelonephritis, AKI, CKD if chronic. Treatment depends on "
             "cause: stone procedures (50590), ureteral stent (50605–50606), nephrostomy (50432). Post-obstructive "
             "polyuria management required.",
         source_document="ICD-10-CM 2025; Urology Guidelines",
         data_confidence=0.93, rule_certainty="guideline"),

    dict(code="N25.9", description="Disorder resulting from impaired renal function, unspecified",
         value_tier="moderate", typical_setting="both",
         settings=["inpatient","outpatient","professional","home_health"],
         valid_as_primary_dx=False,
         audit_notes="Secondary code for CKD complications (renal osteodystrophy, mineral bone disease, "
             "anemia, hypertension, secondary hyperparathyroidism) when primary kidney disease code alone "
             "doesn't capture the full clinical picture. N25.0–N25.8 are more specific (renal osteodystrophy, "
             "rickets, tubular necrosis, etc.). Use as secondary code with primary CKD or ESRD diagnosis. "
             "Phosphate binder use (calcium carbonate, sevelamer CPT 99211) common.",
         source_document="ICD-10-CM 2025; KDIGO CKD-MBD Guidelines",
         data_confidence=0.88, rule_certainty="guideline"),

    dict(code="D64.9", description="Anemia, unspecified",
         value_tier="moderate", typical_setting="both",
         settings=["inpatient","outpatient","professional","home_health","snf"],
         valid_as_primary_dx=False,
         audit_notes="Common comorbidity with CKD/ESRD from erythropoietin deficiency and chronic disease. "
             "When hemoglobin is documented, D63.1 (anemia of chronic kidney disease) is preferred if CKD is "
             "also coded. ESA use (epoetin alfa CPT 90887, darbepoetin alfa 90888) is standard for ESRD anemia. "
             "Ferric carboxymaltose (IV iron, CPT 96369) for IV iron repletion. Iron studies (ferritin CPT 82728, "
             "iron saturation) required for ESA dosing. Hgb target 10–11.5 g/dL per KDIGO.",
         source_document="ICD-10-CM 2025; KDIGO Anemia in CKD Guidelines",
         data_confidence=0.93, rule_certainty="guideline"),
]

# ── Existing codes to update with richer data from this batch ─────────────────
# Keys are code values; values are the fields to update.
# Uses the richer audit_notes and settings from the structured Claude output.
UPDATES = {
    "A41.9": dict(
        audit_notes="One of the highest-dollar inpatient DRGs (870–872). Documentation must clearly "
            "state 'sepsis' per Sepsis-3 criteria; 'possible' or 'probable' sepsis may only be coded "
            "as confirmed in inpatient settings per official guidelines. Frequently scrutinized for "
            "upcoding to severe sepsis (A41.9 + R65.20) or septic shock (R65.21). OIG and RAC auditors "
            "routinely target sepsis claims for medical record review. Second most common SNF DX per "
            "Definitive HC data.",
        applicable_settings=json.dumps(["inpatient","snf","irf"]),
        data_confidence=0.97,
    ),
    "I50.9": dict(
        audit_notes="DRG 291–293 with significant payment variance by CC/MCC. Payers look for "
            "specificity — systolic vs diastolic, acute vs chronic. Home health and SNF claims with "
            "heart failure as primary are high-volume and targeted for homebound criteria validation. "
            "Commonly appears as secondary driving DRG severity. I11.0 required when hypertension "
            "is also documented — coding I10 + I50.9 separately is a sequencing error.",
        applicable_settings=json.dumps(["inpatient","outpatient","professional","snf","home_health","irf"]),
        data_confidence=0.96,
    ),
    "I21.9": dict(
        audit_notes="AMI codes require specificity (STEMI vs NSTEMI, location) when supported by "
            "documentation. I21.9 when more specific codes are available is an upcoding flag. "
            "DRG 280–282 payment varies considerably; MCC documentation (e.g., cardiogenic shock) "
            "must be clinically supported. Post-MI encounters should use I22.x (subsequent MI) or "
            "Z86.19 (history), not I21.x.",
        applicable_settings=json.dumps(["inpatient"]),
        data_confidence=0.95,
    ),
    "J18.9": dict(
        audit_notes="DRG 193–195. Organism specificity (J13 Streptococcal, J15.1 Pseudomonal) "
            "preferred when documented; J18.9 appropriate when organism is unknown. HAP and VAP "
            "have distinct codes (J95.851) and should not be coded as J18.9. Frequently reviewed "
            "in RAC audits for medical necessity of inpatient vs outpatient treatment.",
        applicable_settings=json.dumps(["inpatient","snf","irf"]),
        data_confidence=0.96,
    ),
    "J44.1": dict(
        audit_notes="DRG 190–192. Distinction between J44.0 (with acute lower respiratory infection) "
            "and J44.1 (acute exacerbation) is clinically important and audited. Acute exacerbation "
            "requires documented worsening of baseline COPD, not just a superimposed infection. "
            "Home health claims with COPD are subject to homebound criterion review. Frequently "
            "combined with respiratory failure (J96.x) as MCC.",
        applicable_settings=json.dumps(["inpatient","outpatient","professional","snf","home_health"]),
        data_confidence=0.94,
    ),
    "I63.9": dict(
        audit_notes="DRG 061–066; top IRF qualifying condition under CMS 60% rule. Specificity by "
            "infarct type and vessel (I63.0–I63.5x) is preferred. IRF claims reviewed for functional "
            "status documentation, FIM scores, and IRF vs SNF appropriateness. Stroke onset timing "
            "affects sequencing.",
        applicable_settings=json.dumps(["inpatient","irf"]),
        data_confidence=0.95,
    ),
    "N17.9": dict(
        audit_notes="DRG 682–684; significant MCC as secondary. Requires physician documentation — "
            "creatinine alone insufficient. Distinguish AKI (N17.x) from CKD (N18.x); AKI on CKD "
            "coded N17.9 + N18.x. Dialysis initiation (5A1D) coded separately. RAC auditors target "
            "AKI + sepsis combinations.",
        applicable_settings=json.dumps(["inpatient","snf"]),
        data_confidence=0.94,
    ),
    "G93.41": dict(
        audit_notes="MCC — major DRG severity driver. One of the most commonly queried diagnoses in "
            "CDI programs. Physician documentation must support metabolic etiology rather than presumed "
            "altered mental status. Second most common SNF DX per Definitive HC data (3.30% of SNF "
            "claims). High RAC and MAC audit frequency.",
        applicable_settings=json.dumps(["inpatient","snf"]),
        data_confidence=0.93,
    ),
    "I48.91": dict(
        audit_notes="DRG 308–310. Updated specificity options added FY2020 (I48.11 longstanding "
            "persistent, I48.19 other persistent, I48.20 chronic). Use of I48.91 when more specific "
            "type is documented is a coding specificity flag. High outpatient volume in cardiology. "
            "Anticoagulation management is a common associated service with its own audit exposure.",
        applicable_settings=json.dumps(["inpatient","outpatient","professional"]),
        data_confidence=0.93,
    ),
    "K92.1": dict(
        audit_notes="DRG 377–379. Upper GI bleed with tarry stool presentation (melena = digested "
            "blood). When source of bleed is identified, the underlying condition should be sequenced "
            "as principal rather than the symptom. High inpatient admission rate from ED.",
        applicable_settings=json.dumps(["inpatient","outpatient"]),
        data_confidence=0.91,
    ),
    "A04.72": dict(
        audit_notes="HAC when not POA (POA = N) — CMS does not pay higher severity DRG. POA indicator "
            "is mandatory and directly affects payment. SNFs have high C. diff rates due to antibiotic "
            "use in elderly. Recurrent episodes use A04.71. DRG 371–373.",
        applicable_settings=json.dumps(["inpatient","snf"]),
        data_confidence=0.95,
    ),
    "I26.99": dict(
        audit_notes="DRG 175–176; PE is also a HAC when post-procedure (POA = N). DVT and PE codes "
            "require documentation of acuity and laterality when known. Incidental PE not clinically "
            "treated should not be coded as principal diagnosis. Anticoagulation supports acute PE "
            "coding; chronic PE uses I27.82.",
        applicable_settings=json.dumps(["inpatient"]),
        data_confidence=0.93,
    ),
    "T81.40XA": dict(
        applicable_settings=json.dumps(["inpatient"]),
        data_confidence=0.94,
    ),
    "S72.001A": dict(
        audit_notes="DRG 480–482; top IRF qualifying condition and major SNF post-acute driver. "
            "7th character for encounter type is critical (A=initial, D=subsequent). Surgical repair "
            "codes must align with fracture type and laterality. Post-acute SNF vs IRF placement "
            "decisions are a frequent audit focus.",
        applicable_settings=json.dumps(["inpatient","snf","irf"]),
        data_confidence=0.95,
    ),
    "J96.00": dict(
        audit_notes="MCC — dramatically increases DRG payment. Hypoxic (J96.01) vs hypercapnic "
            "(J96.02) specificity when documented. When respiratory failure is reason for admission, "
            "it is principal; when it develops during admission, it is secondary. Ventilator support "
            "codes must reconcile with the respiratory failure diagnosis.",
        applicable_settings=json.dumps(["inpatient"]),
        data_confidence=0.94,
    ),
    "E87.6": dict(
        audit_notes="Common secondary CC; overuse without clinical documentation of treatment or "
            "monitoring is a CDI audit flag. Lab value alone (K+ <3.5) is insufficient — physician "
            "must document the diagnosis. Electrolyte disorders are among the most queried secondary "
            "diagnoses in CDI programs.",
        applicable_settings=json.dumps(["inpatient"]),
        valid_as_primary_dx=False,
        data_confidence=0.90,
    ),
    "D64.9": dict(
        audit_notes="Extremely high-volume secondary DX; specificity (D50.9, D51.9, D64.81) preferred "
            "when documented. Anemia of chronic disease (D63.1) should be secondary to the underlying "
            "chronic condition. Blood transfusion supports clinical significance. CDI programs "
            "frequently query for anemia specificity.",
        applicable_settings=json.dumps(["inpatient","snf","home_health"]),
        valid_as_primary_dx=False,
        data_confidence=0.91,
    ),
    "I25.10": dict(
        audit_notes="High-volume chronic condition; DRG 302–304 as principal inpatient DX. When "
            "angina is documented, I25.110 (unstable) or I25.119 (other) should be used. Native vs "
            "bypass graft distinction (I25.1x vs I25.7x) is required. Frequently a driver of cardiac "
            "cath and PCI claims in outpatient.",
        applicable_settings=json.dumps(["inpatient","outpatient","professional"]),
        data_confidence=0.92,
    ),
    "N39.0": dict(
        audit_notes="Extremely high-volume across all settings; third most common SNF DX at 2.92% "
            "of claims per Definitive HC. Organism identified → B96.x additional code. CAUTI "
            "(T83.511A) is a HAC category. Pyelonephritis (N10–N12) when upper tract documented.",
        applicable_settings=json.dumps(["inpatient","outpatient","professional","snf","home_health"]),
        data_confidence=0.97,
    ),
    "I10": dict(
        audit_notes="Highest-volume DX in Medicare FFS professional claims. Rarely principal inpatient "
            "DX; typically secondary. I11.x required when both hypertension and heart failure are "
            "documented — coding I10 + I50.9 separately is a sequencing error. Secondary HTN (I15.x) "
            "requires documentation of underlying cause.",
        applicable_settings=json.dumps(["inpatient","outpatient","professional","snf","home_health","irf"]),
        valid_as_primary_dx=False,
        data_confidence=0.98,
    ),
    "E11.9": dict(
        audit_notes="Ubiquitous secondary across all care settings. E11.9 only when no diabetic "
            "complications documented; presence of nephropathy (E11.65), neuropathy (E11.40), "
            "retinopathy (E11.3x), or wound (E11.621) requires more specific combination codes. "
            "Insulin use requires Z79.4. Significant HCC value — affects RAF scores in Medicare "
            "Advantage.",
        applicable_settings=json.dumps(["inpatient","outpatient","professional","snf","home_health","irf"]),
        valid_as_primary_dx=False,
        data_confidence=0.97,
    ),
    "Z51.11": dict(
        audit_notes="Principal DX for chemo encounters; active malignancy (C-code) is secondary per "
            "ICD-10-CM guidelines. DRG 847–848 inpatient; high-dollar outpatient APC. Payers audit "
            "inpatient vs outpatient chemo setting medical necessity. Drug administration CPTs must "
            "align with documented agent and infusion time.",
        applicable_settings=json.dumps(["inpatient","outpatient"]),
        typical_setting="outpatient",
        data_confidence=0.95,
    ),
    "K57.30": dict(
        audit_notes="DRG 391–392 inpatient. Specificity matters — with/without perforation/abscess, "
            "with/without bleeding (K57.30–K57.33). Colonoscopy during acute episode raises medical "
            "necessity questions — guidelines generally recommend deferral. Perforation (K57.20) "
            "carries significantly higher DRG weight and requires clinical documentation support.",
        applicable_settings=json.dumps(["inpatient","outpatient"]),
        data_confidence=0.91,
    ),
    "C34.90": dict(
        audit_notes="Laterality and lobe specificity required when documented. Use C34.90 only when "
            "truly unspecified. Primary (C34.x) vs metastatic (C78.00–C78.02) distinction is critical. "
            "Often triggers medical necessity review for imaging and treatment authorization.",
        applicable_settings=json.dumps(["inpatient","outpatient"]),
        data_confidence=0.93,
    ),
    "G35": dict(
        audit_notes="CMS 60% qualifying condition for IRF. Acute MS exacerbation with functional "
            "decline supports IRF admission; stable MS with only maintenance therapy does not. FIM "
            "scores required at IRF admission and discharge. Expensive DMTs require PA and step "
            "therapy documentation.",
        applicable_settings=json.dumps(["irf","outpatient","professional"]),
        data_confidence=0.94,
    ),
    "G43.909": dict(
        audit_notes="High-volume neurology and PCP. Intractability distinction (G43.919) affects "
            "LCD coverage for Botox (J0585) which requires chronic migraine (G43.709) and failed "
            "preventive medications. CGRP inhibitor prescriptions have specific coverage requirements.",
        applicable_settings=json.dumps(["outpatient","professional"]),
        data_confidence=0.92,
    ),
    "M17.11": dict(
        audit_notes="Laterality (right M17.11, left M17.12, bilateral M17.0) required. Post-TKA, "
            "Z96.641 (prosthesis) is relevant code, not ongoing OA. IRF admission for knee replacement "
            "is a qualified condition under the CMS 60% rule.",
        applicable_settings=json.dumps(["outpatient","professional","snf","irf"]),
        data_confidence=0.94,
    ),
    "Z00.00": dict(
        audit_notes="Preventive visit — triggers specific E&M coding rules (99385–99397). When an "
            "acute problem is addressed at the same visit, separate E&M with modifier 25 may be "
            "appropriate. Z00.01 when abnormal findings are identified. Payers audit modifier 25 "
            "on preventive visit dates for appropriateness. MCE unacceptable as inpatient PDX.",
        applicable_settings=json.dumps(["outpatient","professional"]),
        data_confidence=0.95,
    ),
    "M54.5": dict(
        termination_date="2022-09-30",
        audit_notes="RETIRED effective ICD-10-CM FY2023 (DOS on or after Oct 1 2022). Replaced by "
            "M54.50 (unspecified), M54.51 (vertebrogenic), M54.59 (other). Flag M54.5 on claims "
            "with DOS ≥ 2022-10-01 as an inactive code.",
        applicable_settings=json.dumps(["outpatient","professional"]),
        data_confidence=0.97,
    ),
    "R07.9": dict(
        audit_notes="High-volume ED and outpatient symptom code; appropriate for initial presentation "
            "before workup complete. More specific codes (R07.1 atypical, R07.89 other) preferred "
            "when available. When cardiac origin confirmed, specific cardiac DX should replace. "
            "Paired with CXR or cardiac imaging, medical necessity is usually supportable.",
        applicable_settings=json.dumps(["outpatient","professional"]),
        typical_setting="ed",
        data_confidence=0.94,
    ),
    "Z87.39": dict(
        typical_setting="both",
        applicable_settings=json.dumps(["home_health","snf","outpatient"]),
        audit_notes="History/aftercare code — MCE unacceptable as inpatient principal DX. Should "
            "only appear as secondary DX. For home health, active primary diagnosis must drive the "
            "skilled service need; history code alone does not support home health eligibility. "
            "OASIS assessment must document specific skilled nursing or therapy needs.",
        data_confidence=0.87,
    ),
}


def run(db_path: str = DB_PATH) -> int:
    conn = sqlite3.connect(db_path)
    inserted = updated = 0
    try:
        for entry in CODES:
            code = entry["code"]
            settings_json = json.dumps(entry.get("settings", []))
            conn.execute(
                "INSERT OR IGNORE INTO icd_codes "
                "(icd_code_id, code, description, code_type, value_tier, chapter, "
                "is_manifestation, is_etiology, typical_setting, applicable_settings, "
                "valid_as_primary_dx, termination_date, audit_notes, "
                "source_authority, source_document, source_url, last_reviewed_at, "
                "data_confidence, data_confidence_notes, rule_certainty, "
                "created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()), code, entry["description"], "icd10_cm",
                    entry["value_tier"], _chapter(code),
                    0, 0,
                    entry["typical_setting"], settings_json,
                    int(entry.get("valid_as_primary_dx", True)),
                    entry.get("termination_date"),
                    entry.get("audit_notes"),
                    "CMS", entry.get("source_document", "ICD-10-CM 2025"),
                    "https://www.cms.gov/medicare/coding-billing/icd-10-codes",
                    "2025-01-01",
                    entry.get("data_confidence", 0.90),
                    "Structured output from Claude (claude.ai) validated against ICD-10-CM 2025",
                    entry.get("rule_certainty", "guideline"),
                    NOW, NOW,
                ),
            )
            if conn.execute("SELECT changes()").fetchone()[0]:
                inserted += 1

        for code, fields in UPDATES.items():
            set_parts = ", ".join(f"{k} = ?" for k in fields)
            vals = list(fields.values()) + [code]
            conn.execute(f"UPDATE icd_codes SET {set_parts}, updated_at = ? WHERE code = ?",
                         vals[:-1] + [NOW, code])
            if conn.execute("SELECT changes()").fetchone()[0]:
                updated += 1

        conn.commit()
        print(f"  Extended ICD-10: {inserted} inserted, {updated} updated")
        return inserted + updated
    finally:
        conn.close()


if __name__ == "__main__":
    run()
