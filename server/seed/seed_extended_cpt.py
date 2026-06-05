"""Upsert CPT/HCPCS codes, extend cpt_dx_coverage and cpt_modifier_map.

Source: Claude (claude.ai) structured output validated against CPT 2025,
CMS PFS FY2025, NCCI edits, and setting-specific LCD/coverage documentation.

Run standalone:  python seed/seed_extended_cpt.py
"""
from __future__ import annotations

import json
import os
import sqlite3
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW = "2025-01-01T00:00:00"

# ── New modifiers not yet in modifier_codes ────────────────────────────────────
# (code, description, modifier_type, applies_to, payment_impact, payment_factor,
#  ncci_override, requires_documentation, audit_risk_score, audit_notes,
#  source_authority, source_document)
NEW_MODIFIERS = [
    ("95",  "Synchronous telemedicine service rendered via real-time interactive audio and video telecommunications system",
     "service", "both", "none", None, False, False, 0.25,
     "Required for synchronous telehealth services. AV technology must be documented; audio-only requires FQ.",
     "AMA", "CPT 2025 Appendix P"),
    ("FQ",  "Service furnished using audio-only communication technology",
     "service", "cpt",  "none", None, False, True,  0.45,
     "Medicare audio-only telehealth modifier. PHE extension required; document why video not available.",
     "CMS", "CMS Telehealth Policy 2025"),
    ("AI",  "Principal physician of record",
     "informational", "cpt", "none", None, False, False, 0.15,
     "Required on Medicare when attending physician bills subsequent hospital visits as principal physician.",
     "CMS", "CMS PFS FY2025"),
    ("RT",  "Right side",
     "informational", "both", "none", None, False, False, 0.10,
     "Laterality modifier for right-side procedures. Required by many payers for bilateral-eligible codes.",
     "CMS", "CMS PFS FY2025"),
    ("LT",  "Left side",
     "informational", "both", "none", None, False, False, 0.10,
     "Laterality modifier for left-side procedures.",
     "CMS", "CMS PFS FY2025"),
    ("KX",  "Requirements specified in the medical policy have been met",
     "informational", "both", "none", None, False, True,  0.30,
     "Medicare modifier attesting documentation supports coverage criteria (therapy caps, CPAP, DME). Required on qualifying claims.",
     "CMS", "CMS PFS FY2025"),
    ("GP",  "Services delivered under an outpatient physical therapy plan of care",
     "informational", "cpt",  "none", None, False, False, 0.10,
     "Required on PT services under Medicare Part B. Plan of care must be on file.",
     "CMS", "CMS PFS FY2025"),
    ("GO",  "Services delivered under an outpatient occupational therapy plan of care",
     "informational", "cpt",  "none", None, False, False, 0.10,
     "Required on OT services under Medicare Part B.",
     "CMS", "CMS PFS FY2025"),
    ("78",  "Unplanned return to the operating/procedure room by the same physician following initial procedure for a related procedure during the postoperative period",
     "informational", "cpt", "reduce", 0.70, False, True, 0.30,
     "Return to OR for related complication within global period. 70% of surgical fee. Document clinical necessity clearly.",
     "AMA", "CPT 2025 Appendix A"),
    ("PT",  "Colorectal cancer screening test; converted to diagnostic test or other procedure",
     "informational", "cpt", "none", None, False, False, 0.20,
     "Medicare: screening colonoscopy that becomes diagnostic/therapeutic. Reduces patient cost-sharing. Required when Z12.11 claim includes polypectomy.",
     "CMS", "CMS PFS FY2025"),
    ("33",  "Preventive service",
     "informational", "both", "none", None, False, False, 0.10,
     "ACA-compliant plans: waives patient cost-sharing for USPSTF grade A/B preventive services. Distinct from Medicare modifier PT.",
     "CMS", "ACA Section 2713"),
    ("LD",  "Left anterior descending coronary artery",
     "informational", "cpt", "none", None, False, False, 0.10,
     "Vessel identification for PCI/cath procedures. Required to specify vessel treated.",
     "CMS", "CMS PFS FY2025"),
    ("RC",  "Right coronary artery",
     "informational", "cpt", "none", None, False, False, 0.10,
     "Vessel identification for PCI/cath procedures.",
     "CMS", "CMS PFS FY2025"),
    ("LC",  "Left circumflex coronary artery",
     "informational", "cpt", "none", None, False, False, 0.10,
     "Vessel identification for PCI/cath procedures.",
     "CMS", "CMS PFS FY2025"),
    ("GG",  "Performance and payment of a screening mammogram and diagnostic mammogram on the same patient, same day",
     "informational", "cpt", "none", None, False, False, 0.20,
     "Required when screening and diagnostic mammogram performed same day. Affects APC assignment and cost-sharing.",
     "CMS", "CMS OPPS"),
    ("JW",  "Drug amount discarded/not administered to any patient",
     "informational", "hcpcs", "none", None, False, True, 0.35,
     "Required for wasted single-dose vial portion. Units billed = administered + JW discarded units. OIG reviews for accuracy.",
     "CMS", "CMS PFS FY2025"),
    ("Q7",  "One Class A finding",
     "informational", "hcpcs", "none", None, False, True, 0.25,
     "Lower extremity wound qualifier for skin substitute claims. One of three Classes A/B/C required for coverage.",
     "CMS", "CMS LCD L39012"),
    ("GA",  "Waiver of liability statement issued as required by payer policy, individual case",
     "informational", "both", "none", None, False, True, 0.20,
     "ABN on file for this service. Required when billing non-covered items to beneficiary.",
     "CMS", "CMS Pub 100-04 Ch. 30"),
    ("GX",  "Notice of liability issued, voluntary under payer policy",
     "informational", "both", "none", None, False, True, 0.15,
     "Voluntary ABN issued. Used when non-coverage is expected but not certain.",
     "CMS", "CMS Pub 100-04 Ch. 30"),
    ("HQ",  "Group setting",
     "service", "both", "none", None, False, True, 0.30,
     "Required by some Medicaid programs for group therapy billing. Document group size and each patient note.",
     "CMS", "SAMHSA/Medicaid"),
    ("NU",  "New equipment",
     "informational", "hcpcs", "none", None, False, False, 0.10,
     "DME purchased new. Distinguishes from RR (rental) for DMEPOS billing.",
     "CMS", "CMS DMEPOS"),
    ("RR",  "Rental",
     "informational", "hcpcs", "reduce", None, False, False, 0.10,
     "DME rental billing. Monthly rental payments; capped at purchase price per CMS policy.",
     "CMS", "CMS DMEPOS"),
]

# ── CPT/HCPCS codes ────────────────────────────────────────────────────────────
# Each dict: all CPT columns + dx_coverage list + valid_modifiers list

CODES = [
    # ── E&M — OFFICE / OUTPATIENT ──────────────────────────────────────────
    dict(
        code="99213", description="Office or other outpatient visit, established patient, low medical decision making",
        code_type="cpt", value_tier="low", typical_setting="professional",
        applicable_settings=["professional","outpatient"],
        risk_score=0.55, typical_units_max=1, requires_auth=False,
        specialty_typical="Primary Care", is_add_on=False, global_period_days=0,
        audit_notes="High-volume E&M code; most common established patient visit level. Requires MDM documenting low complexity or total time 20–29 minutes per 2021 E&M guidelines. Audit risk centers on downcoding (using 99213 when 99214 is documented) and upcoding (using 99213 with inadequate documentation). Modifier 25 required when a procedure is performed same day. CMS has flagged providers whose 99213 distribution is an outlier vs specialty peers.",
        source_document="CPT 2025; CMS PFS FY2025; AMA E&M Guidelines 2021",
        data_confidence=0.97, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="I10",   coverage_type="supporting", rationale="HTN management visit supports 99213 low MDM"),
            dict(icd_code="E11.9", coverage_type="supporting", rationale="Routine DM follow-up supports low-moderate MDM"),
            dict(icd_code="Z00.00",coverage_type="excluded",   rationale="Preventive visit — use 99395-99397; bill 99213 separately with mod 25 only if acute problem addressed"),
        ],
        valid_modifiers=[
            dict(modifier_code="25", ncci_override=True,  payment_factor=1.0, notes="Required when procedure billed same day; E&M must be separately documented"),
            dict(modifier_code="95", ncci_override=False, payment_factor=1.0, notes="Telehealth synchronous visit"),
            dict(modifier_code="GT", ncci_override=False, payment_factor=1.0, notes="Medicare telehealth via interactive audio/video"),
        ],
    ),
    dict(
        code="99214", description="Office or other outpatient visit, established patient, moderate medical decision making",
        code_type="cpt", value_tier="moderate", typical_setting="professional",
        applicable_settings=["professional","outpatient"],
        risk_score=0.65, typical_units_max=1, requires_auth=False,
        specialty_typical="Primary Care", is_add_on=False, global_period_days=0,
        audit_notes="The single highest-volume CPT code in Medicare FFS professional claims. Requires moderate MDM (2+ problems, prescription drug management, or moderate-risk decisions) or 30–39 minutes total time. Payers audit providers whose 99214 percentage exceeds specialty benchmark significantly. Common error: billing 99214 with documentation that only supports 99213 MDM level. Split/shared visits require attestation of the substantive portion performed by billing provider.",
        source_document="CPT 2025; CMS PFS FY2025; AMA E&M Guidelines 2021",
        data_confidence=0.98, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="I50.9", coverage_type="supporting", rationale="CHF management with medication adjustment supports moderate MDM"),
            dict(icd_code="E11.9", coverage_type="supporting", rationale="DM with insulin management supports moderate MDM"),
            dict(icd_code="Z00.00",coverage_type="excluded",   rationale="Not for preventive visits; use preventive codes with mod 25 for concurrent acute problem"),
        ],
        valid_modifiers=[
            dict(modifier_code="25", ncci_override=True,  payment_factor=1.0, notes="Procedure same day — E&M must be separately documented and medically necessary"),
            dict(modifier_code="95", ncci_override=False, payment_factor=1.0, notes="Telehealth"),
            dict(modifier_code="FQ", ncci_override=False, payment_factor=1.0, notes="Audio-only Medicare telehealth visit"),
        ],
    ),
    dict(
        code="99215", description="Office or other outpatient visit, established patient, high medical decision making",
        code_type="cpt", value_tier="moderate", typical_setting="professional",
        applicable_settings=["professional","outpatient"],
        risk_score=0.75, typical_units_max=1, requires_auth=False,
        specialty_typical="Internal Medicine", is_add_on=False, global_period_days=0,
        audit_notes="Highest-level established patient office visit; requires high MDM (3+ problems, drug therapy requiring intensive monitoring, or high-risk decisions such as hospitalization) or ≥40 minutes total time. Significant audit risk when billed disproportionately vs specialty peers. Providers billing 99215 for >50% of established patients without supporting documentation are a payer outlier flag. Time-based billing requires contemporaneous documentation of total time and nature of activities.",
        source_document="CPT 2025; CMS PFS FY2025; AMA E&M Guidelines 2021",
        data_confidence=0.96, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="A41.9", coverage_type="supporting", rationale="Sepsis management or post-discharge follow-up supports high MDM"),
            dict(icd_code="C34.90",coverage_type="supporting", rationale="Active malignancy management with complex treatment decisions"),
        ],
        valid_modifiers=[
            dict(modifier_code="25", ncci_override=True,  payment_factor=1.0, notes="Procedure same day"),
            dict(modifier_code="95", ncci_override=False, payment_factor=1.0, notes="Synchronous telehealth"),
        ],
    ),
    dict(
        code="99203", description="Office or other outpatient visit, new patient, low medical decision making",
        code_type="cpt", value_tier="moderate", typical_setting="professional",
        applicable_settings=["professional","outpatient"],
        risk_score=0.50, typical_units_max=1, requires_auth=False,
        specialty_typical="Primary Care", is_add_on=False, global_period_days=0,
        audit_notes="New patient visit requires all 3 key components (or time) since no prior established relationship. New patient definition: not seen by provider or same group/specialty in past 3 years. Low MDM or 30–44 minutes total time. Common audit finding: using new patient codes for patients with prior visits or in same practice group. Payers flag high new-to-established patient ratios as a potential upcoding indicator.",
        source_document="CPT 2025; CMS PFS FY2025",
        data_confidence=0.95, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="E78.5", coverage_type="supporting", rationale="New patient presenting with hyperlipidemia for management"),
            dict(icd_code="M54.50",coverage_type="supporting", rationale="New patient presenting with low back pain"),
        ],
        valid_modifiers=[
            dict(modifier_code="25", ncci_override=True,  payment_factor=1.0, notes="Procedure same day; documentation must support both"),
            dict(modifier_code="95", ncci_override=False, payment_factor=1.0, notes="Telehealth"),
        ],
    ),
    dict(
        code="99205", description="Office or other outpatient visit, new patient, high medical decision making",
        code_type="cpt", value_tier="high", typical_setting="professional",
        applicable_settings=["professional","outpatient"],
        risk_score=0.72, typical_units_max=1, requires_auth=False,
        specialty_typical="Specialist", is_add_on=False, global_period_days=0,
        audit_notes="Highest-level new patient visit; requires high MDM or ≥60 minutes total time. High audit risk when billed for new specialty consultations that don't document complexity sufficient for high MDM. Referral from PCP does not automatically qualify as high MDM. OIG has flagged oncology, neurology, and cardiology practices for disproportionate 99205 billing. Must document all conditions addressed and decision-making complexity.",
        source_document="CPT 2025; CMS PFS FY2025",
        data_confidence=0.94, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="C34.90",coverage_type="supporting", rationale="New oncology patient with complex treatment planning"),
            dict(icd_code="I50.9", coverage_type="supporting", rationale="New cardiology patient with decompensated heart failure"),
        ],
        valid_modifiers=[
            dict(modifier_code="25", ncci_override=True, payment_factor=1.0, notes="Procedure same day"),
        ],
    ),
    # ── E&M — INPATIENT ────────────────────────────────────────────────────
    dict(
        code="99232", description="Subsequent hospital care, moderate medical decision making",
        code_type="cpt", value_tier="moderate", typical_setting="inpatient",
        applicable_settings=["inpatient"],
        risk_score=0.68, typical_units_max=1, requires_auth=False,
        specialty_typical="Hospitalist", is_add_on=False, global_period_days=0,
        audit_notes="Most common subsequent inpatient visit code; requires moderate MDM or 25–34 minutes total time. Payers audit for daily rounding visits that exceed expected LOS without supporting MDM. Hospitalists billing 99233 (high MDM) for every inpatient day are a red flag. Split/shared inpatient visits between physician and APP require clear documentation of the substantive portion. Must reflect unique medical necessity for each day billed.",
        source_document="CPT 2025; CMS PFS FY2025; AMA E&M Guidelines 2021",
        data_confidence=0.95, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="A41.9", coverage_type="supporting", rationale="Daily sepsis management supports moderate MDM"),
            dict(icd_code="J18.9", coverage_type="supporting", rationale="Inpatient pneumonia daily management"),
        ],
        valid_modifiers=[
            dict(modifier_code="AI", ncci_override=False, payment_factor=1.0, notes="Principal physician of record — required for Medicare attending billing subsequent visits"),
        ],
    ),
    dict(
        code="99291", description="Critical care, evaluation and management of the critically ill, first 30-74 minutes",
        code_type="cpt", value_tier="high", typical_setting="inpatient",
        applicable_settings=["inpatient","outpatient"],
        risk_score=0.82, typical_units_max=1, requires_auth=False,
        specialty_typical="Critical Care / Intensivist", is_add_on=False, global_period_days=0,
        audit_notes="Critical care requires documentation that the patient has a critical illness (vital organ failure or risk of imminent deterioration) AND ≥30 minutes direct care. Time must be documented contemporaneously. Procedures with separate CPT codes (central line 36556, intubation 31500) must be billed separately and their time excluded from critical care time. Common audit finding: billing 99291 for patients who do not meet the 'critical illness' threshold. Cannot be billed same day as consultations (99251-99255) by same provider.",
        source_document="CPT 2025; CMS PFS FY2025; AMA Critical Care Guidelines",
        data_confidence=0.94, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="A41.9", coverage_type="required",  rationale="Septic shock with organ dysfunction supports critical care level"),
            dict(icd_code="J96.00",coverage_type="required",  rationale="Acute respiratory failure requiring active management"),
            dict(icd_code="J18.9", coverage_type="excluded",  rationale="Pneumonia alone without organ dysfunction does not qualify as critical illness"),
        ],
        valid_modifiers=[
            dict(modifier_code="AI", ncci_override=False, payment_factor=1.0, notes="Principal physician of record"),
        ],
    ),
    dict(
        code="99292", description="Critical care, each additional 30 minutes",
        code_type="cpt", value_tier="moderate", typical_setting="inpatient",
        applicable_settings=["inpatient"],
        risk_score=0.78, typical_units_max=4, requires_auth=False,
        specialty_typical="Critical Care / Intensivist", is_add_on=True, global_period_days=0,
        audit_notes="Add-on to 99291; each unit represents 30 additional minutes of critical care. Max 4 units/day in most scenarios. Total documented time must reconcile with units billed — 1 unit of 99292 requires 75–104 minutes total, 2 units requires 105–134 minutes. Payers audit for time documentation inconsistencies. Procedures bundled into critical care time are the most common documentation error.",
        source_document="CPT 2025; CMS PFS FY2025",
        data_confidence=0.93, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="A41.9", coverage_type="required", rationale="Must meet critical illness threshold — same as 99291"),
        ],
        valid_modifiers=[],
    ),
    # ── CRITICAL CARE PROCEDURES ───────────────────────────────────────────
    dict(
        code="31500", description="Intubation, endotracheal, emergency procedure",
        code_type="cpt", value_tier="high", typical_setting="inpatient",
        applicable_settings=["inpatient","outpatient"],
        risk_score=0.60, typical_units_max=1, requires_auth=False,
        specialty_typical="Emergency Medicine / Critical Care", is_add_on=False, global_period_days=0,
        audit_notes="Separately billable from critical care when performed by a different provider; cannot be billed separately by the same provider billing 99291 on the same date — time must be deducted from critical care total. Requires documentation of indication, technique, confirmation of placement, and response. Common audit finding: same provider billing both 31500 and 99291 on same day. Elective intubation for surgical cases is not separately billable.",
        source_document="CPT 2025; CMS PFS FY2025; AMA Critical Care FAQ",
        data_confidence=0.92, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="J96.00",coverage_type="required",  rationale="Acute respiratory failure is primary indication"),
            dict(icd_code="A41.9", coverage_type="supporting",rationale="Sepsis with respiratory compromise"),
        ],
        valid_modifiers=[
            dict(modifier_code="59", ncci_override=True, payment_factor=1.0, notes="Distinct procedure when different provider bills intubation vs critical care"),
        ],
    ),
    dict(
        code="36556", description="Insertion of non-tunneled centrally inserted central venous catheter, age 5 years or older",
        code_type="cpt", value_tier="high", typical_setting="inpatient",
        applicable_settings=["inpatient","outpatient"],
        risk_score=0.65, typical_units_max=1, requires_auth=False,
        specialty_typical="Critical Care / Surgery", is_add_on=False, global_period_days=0,
        audit_notes="Central line insertion is separately billable from critical care when performed by same provider — time must be excluded from critical care total. Documentation must include indication, site, technique, and confirmation (CXR or ultrasound). CLABSI prevention bundle documentation is a CMS quality measure. Payers audit for medically necessary indication. Ultrasound guidance (76937) frequently billed concurrently and requires real-time imaging documentation.",
        source_document="CPT 2025; CMS PFS FY2025; CMS HAC CLABSI Policy",
        data_confidence=0.92, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="A41.9", coverage_type="supporting",rationale="Sepsis requiring vasopressors or multiple IV medications"),
            dict(icd_code="N17.9", coverage_type="supporting",rationale="AKI with dialysis need"),
        ],
        valid_modifiers=[
            dict(modifier_code="59", ncci_override=True, payment_factor=1.0, notes="Distinct procedure from critical care on same date"),
        ],
    ),
    # ── GI ─────────────────────────────────────────────────────────────────
    dict(
        code="45378", description="Colonoscopy, flexible; diagnostic, including collection of specimen(s) by brushing or washing, when performed",
        code_type="cpt", value_tier="high", typical_setting="outpatient",
        applicable_settings=["outpatient","asc"],
        risk_score=0.72, typical_units_max=1, requires_auth=True,
        specialty_typical="Gastroenterology", is_add_on=False, global_period_days=0,
        audit_notes="Highest-volume GI procedure; significant audit risk around screening vs diagnostic distinction, which affects patient cost-sharing and payer reimbursement. When polyps are found during a scheduled screening colonoscopy, payers differ on whether the encounter becomes diagnostic. Bundling rules: 45378 cannot be billed with 45380 (biopsy) or 45385 (polypectomy) — use the interventional code instead. Anesthesia (MAC) for colonoscopy requires separate documentation of medical necessity.",
        source_document="CPT 2025; CMS OPPS; NCCI Edits; ACG Colonoscopy Guidelines",
        data_confidence=0.96, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="Z12.11",coverage_type="required",  rationale="Screening indication — no patient cost-sharing for Medicare preventive benefit"),
            dict(icd_code="K92.1", coverage_type="supporting",rationale="Diagnostic indication for GI bleeding workup"),
            dict(icd_code="K57.30",coverage_type="supporting",rationale="Diverticular disease follow-up"),
        ],
        valid_modifiers=[
            dict(modifier_code="PT", ncci_override=False, payment_factor=None, notes="Medicare: colorectal cancer screening converted to diagnostic — reduces cost-sharing"),
            dict(modifier_code="33", ncci_override=False, payment_factor=None, notes="Preventive service; waives cost-sharing for ACA-compliant plans"),
            dict(modifier_code="53", ncci_override=False, payment_factor=0.5,  notes="Discontinued procedure; reduced payment when stopped before completion"),
        ],
    ),
    dict(
        code="45385", description="Colonoscopy, flexible; with removal of tumor(s), polyp(s), or other lesion(s) by snare technique",
        code_type="cpt", value_tier="high", typical_setting="outpatient",
        applicable_settings=["outpatient","asc"],
        risk_score=0.70, typical_units_max=1, requires_auth=True,
        specialty_typical="Gastroenterology", is_add_on=False, global_period_days=0,
        audit_notes="Replaces 45378 when polypectomy is performed — 45378 and 45385 cannot be billed together for the same encounter (NCCI bundling). Cold snare (45385) vs cold biopsy (45380) vs hot snare/EMR (45388) distinction must be supported by documentation of technique. Multiple polyp removals at same session do not increase units — one code covers the entire session. Pathology specimen (88305) is separately billable.",
        source_document="CPT 2025; CMS OPPS; NCCI Edits; ACG Guidelines",
        data_confidence=0.95, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="K63.5", coverage_type="required",  rationale="Polyp of colon — found during screening or diagnostic colonoscopy"),
            dict(icd_code="Z12.11",coverage_type="supporting",rationale="Screening colonoscopy that becomes therapeutic when polyp found"),
        ],
        valid_modifiers=[
            dict(modifier_code="PT", ncci_override=False, payment_factor=None, notes="Screening converted to therapeutic; cost-sharing waiver for ACA plans"),
        ],
    ),
    # ── ORTHOPEDIC SURGERY ─────────────────────────────────────────────────
    dict(
        code="27447", description="Arthroplasty, knee, condyle and plateau; medial AND lateral compartments with or without patella resurfacing",
        code_type="cpt", value_tier="high", typical_setting="outpatient",
        applicable_settings=["inpatient","outpatient","asc"],
        risk_score=0.68, typical_units_max=1, requires_auth=True,
        specialty_typical="Orthopedic Surgery", is_add_on=False, global_period_days=90,
        audit_notes="Total knee replacement; 90-day global period — all E&M and related services within 90 days post-op are bundled into the surgical fee. CMS removed TKA from the inpatient-only list in 2018; now commonly performed in outpatient/ASC for appropriate patients. Pre-authorization universal. Common audit finding: billing post-op E&M without modifier 24 (unrelated) or 79 (unrelated procedure) during global period. Implant costs are not separately billable to CMS.",
        source_document="CPT 2025; CMS PFS FY2025; CMS Inpatient-Only List FY2025",
        data_confidence=0.95, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="M17.11",coverage_type="required",  rationale="Primary OA right knee is primary indication"),
            dict(icd_code="M17.12",coverage_type="required",  rationale="Primary OA left knee"),
            dict(icd_code="M17.0", coverage_type="supporting",rationale="Bilateral OA — may require bilateral modifier or two separate claims"),
        ],
        valid_modifiers=[
            dict(modifier_code="50", ncci_override=False, payment_factor=1.5, notes="Bilateral procedure same session; 150% of unilateral fee"),
            dict(modifier_code="RT", ncci_override=False, payment_factor=1.0, notes="Right side"),
            dict(modifier_code="LT", ncci_override=False, payment_factor=1.0, notes="Left side"),
            dict(modifier_code="24", ncci_override=False, payment_factor=1.0, notes="Unrelated E&M during global period"),
            dict(modifier_code="79", ncci_override=False, payment_factor=1.0, notes="Unrelated procedure during global period"),
        ],
    ),
    dict(
        code="27130", description="Arthroplasty, acetabular and proximal femoral prosthetic replacement (total hip arthroplasty)",
        code_type="cpt", value_tier="high", typical_setting="outpatient",
        applicable_settings=["inpatient","outpatient","asc"],
        risk_score=0.65, typical_units_max=1, requires_auth=True,
        specialty_typical="Orthopedic Surgery", is_add_on=False, global_period_days=90,
        audit_notes="Total hip replacement; removed from CMS inpatient-only list in 2020. 90-day global period applies. Payers require documentation of conservative treatment failure (PT, NSAIDs, injections) prior to authorization. Post-op complications (dislocation, infection, aseptic loosening) are separately billable outside the global period with modifier 78 (related return to OR). CMS monitors 30-day readmission rates for THA as a quality measure.",
        source_document="CPT 2025; CMS PFS FY2025; CMS Inpatient-Only List",
        data_confidence=0.95, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="M16.11",  coverage_type="required",  rationale="Primary OA right hip — primary indication"),
            dict(icd_code="S72.001A",coverage_type="supporting",rationale="Femoral neck fracture requiring prosthetic replacement"),
        ],
        valid_modifiers=[
            dict(modifier_code="50", ncci_override=False, payment_factor=1.5, notes="Bilateral THA same session — rare; requires separate documentation"),
            dict(modifier_code="78", ncci_override=False, payment_factor=None, notes="Return to OR for complication during global period"),
            dict(modifier_code="RT", ncci_override=False, payment_factor=1.0, notes="Right hip"),
            dict(modifier_code="LT", ncci_override=False, payment_factor=1.0, notes="Left hip"),
        ],
    ),
    dict(
        code="27245", description="Treatment of intertrochanteric, peritrochanteric, or subtrochanteric femoral fracture; with intramedullary implant, with or without interlocking screws and/or cerclage",
        code_type="cpt", value_tier="high", typical_setting="inpatient",
        applicable_settings=["inpatient"],
        risk_score=0.58, typical_units_max=1, requires_auth=False,
        specialty_typical="Orthopedic Surgery", is_add_on=False, global_period_days=90,
        audit_notes="Surgical treatment of hip fracture; inpatient setting standard given fracture severity and comorbidities. CMS quality measure: time to surgery within 48 hours affects hospital payment. Post-acute care (SNF, IRF, home health) following hip fracture repair is a major utilization management focus. 90-day global period — post-op complications using modifier 78 for return to OR. Documentation must include fracture classification, implant choice rationale, and intraoperative findings.",
        source_document="CPT 2025; CMS PFS FY2025; CMS Hip Fracture Quality Measure",
        data_confidence=0.92, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="S72.001A",coverage_type="required",rationale="Femur fracture initial encounter — primary indication"),
        ],
        valid_modifiers=[
            dict(modifier_code="78", ncci_override=False, payment_factor=None, notes="Return to OR for related complication within global period"),
        ],
    ),
    dict(
        code="29881", description="Arthroscopy, knee, surgical; with meniscectomy (medial OR lateral, including any meniscal shaving)",
        code_type="cpt", value_tier="high", typical_setting="asc",
        applicable_settings=["outpatient","asc"],
        risk_score=0.72, typical_units_max=1, requires_auth=True,
        specialty_typical="Orthopedic Surgery", is_add_on=False, global_period_days=90,
        audit_notes="Arthroscopic meniscectomy for degenerative meniscal tears in patients with OA has been significantly scrutinized — multiple RCTs show no benefit over PT for degenerative tears. CMS and commercial payers increasingly require documentation of acute traumatic tear or failure of conservative treatment. Cannot bill 29881 (medial) and 29882 (lateral) together — use 29883 for both. Diagnostic arthroscopy (29870) is bundled into surgical arthroscopy and cannot be billed separately.",
        source_document="CPT 2025; CMS PFS FY2025; NEJM Meniscectomy Trial Data; NCCI",
        data_confidence=0.92, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="M23.200",coverage_type="required",  rationale="Derangement of unspecified meniscus due to old tear or injury"),
            dict(icd_code="M17.11", coverage_type="excluded",  rationale="OA alone without documented meniscal tear does not support meniscectomy per current evidence"),
        ],
        valid_modifiers=[
            dict(modifier_code="RT", ncci_override=False, payment_factor=1.0, notes="Right knee"),
            dict(modifier_code="LT", ncci_override=False, payment_factor=1.0, notes="Left knee"),
        ],
    ),
    dict(
        code="20610", description="Arthrocentesis, aspiration and/or injection, major joint or bursa; without ultrasound guidance",
        code_type="cpt", value_tier="moderate", typical_setting="professional",
        applicable_settings=["professional","outpatient"],
        risk_score=0.60, typical_units_max=1, requires_auth=False,
        specialty_typical="Orthopedic Surgery / Rheumatology", is_add_on=False, global_period_days=0,
        audit_notes="High-volume injection procedure; frequency rules apply — most payers limit corticosteroid injections to 3–4 per year per joint. Documentation must include injection site, substance injected, and clinical indication. Hyaluronic acid injections for knee OA have specific coverage criteria and are non-covered by Medicare for non-FDA-approved agents. Cannot bill E&M (99213/99214) and 20610 on same date without modifier 25 on E&M. Ultrasound guidance adds 76942.",
        source_document="CPT 2025; CMS PFS FY2025; CMS NCD 150.3 (Viscosupplementation); NCCI",
        data_confidence=0.93, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="M17.11",coverage_type="required",  rationale="Knee OA — primary indication for joint injection"),
            dict(icd_code="M06.9", coverage_type="supporting",rationale="RA joint injection during flare"),
        ],
        valid_modifiers=[
            dict(modifier_code="25", ncci_override=True,  payment_factor=1.0, notes="On E&M code when billed same day as injection"),
            dict(modifier_code="RT", ncci_override=False, payment_factor=1.0, notes="Right joint"),
            dict(modifier_code="LT", ncci_override=False, payment_factor=1.0, notes="Left joint"),
        ],
    ),
    dict(
        code="62321", description="Injection(s), of diagnostic or therapeutic substance(s), interlaminar epidural or subarachnoid, cervical or thoracic; with imaging guidance (fluoroscopy or CT)",
        code_type="cpt", value_tier="high", typical_setting="outpatient",
        applicable_settings=["professional","outpatient","asc"],
        risk_score=0.80, typical_units_max=1, requires_auth=True,
        specialty_typical="Pain Management / Anesthesiology", is_add_on=False, global_period_days=0,
        audit_notes="One of the highest audit-risk pain management codes. LCDs require documentation of conservative treatment failure (typically 6 weeks of PT and medications), imaging evidence of pathology, and specific dermatomal or axial pain pattern. Fluoroscopy (77003) is bundled into 62321 and cannot be billed separately. Frequency limits: CMS limits to 3 injections per region per year. Billing 62321 without fluoroscopy documentation is fraud — use 62320.",
        source_document="CPT 2025; CMS PFS FY2025; CMS LCD L34010; NCCI",
        data_confidence=0.94, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="M54.2", coverage_type="required",  rationale="Cervicalgia with radiculopathy supporting cervical ESI"),
            dict(icd_code="M54.50",coverage_type="supporting",rationale="Low back pain — for lumbar ESI (62323)"),
        ],
        valid_modifiers=[
            dict(modifier_code="50", ncci_override=False, payment_factor=1.5, notes="Bilateral injection same level same session"),
            dict(modifier_code="59", ncci_override=True,  payment_factor=1.0, notes="Distinct service when multiple levels injected"),
        ],
    ),
    # ── OPHTHALMOLOGY ──────────────────────────────────────────────────────
    dict(
        code="66984", description="Extracapsular cataract removal with insertion of intraocular lens prosthesis (1-stage procedure), manual or mechanical technique",
        code_type="cpt", value_tier="high", typical_setting="asc",
        applicable_settings=["outpatient","asc"],
        risk_score=0.60, typical_units_max=1, requires_auth=True,
        specialty_typical="Ophthalmology", is_add_on=False, global_period_days=90,
        audit_notes="Highest-volume Medicare surgical procedure. ASC is the standard setting; inpatient cataract surgery requires justification. Premium IOL upgrades are non-covered by Medicare — facility and physician must issue an ABN and bill separately from covered 66984 services. Visual acuity documentation is required for medical necessity. OIG has investigated unnecessary cataract surgery in patients with minimal visual impairment. Bilateral same-day surgery requires bilateral modifier and payer-specific documentation.",
        source_document="CPT 2025; CMS ASC Covered Procedures; CMS NCD 80.8; OIG Advisory",
        data_confidence=0.96, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="H26.9", coverage_type="required",  rationale="Cataract diagnosis required; specificity preferred"),
            dict(icd_code="H25.11",coverage_type="supporting",rationale="Age-related nuclear cataract right eye — more specific"),
        ],
        valid_modifiers=[
            dict(modifier_code="RT", ncci_override=False, payment_factor=1.0, notes="Right eye"),
            dict(modifier_code="LT", ncci_override=False, payment_factor=1.0, notes="Left eye"),
            dict(modifier_code="50", ncci_override=False, payment_factor=1.5, notes="Bilateral same session"),
        ],
    ),
    # ── CARDIOLOGY ─────────────────────────────────────────────────────────
    dict(
        code="93000", description="Electrocardiogram, routine ECG with at least 12 leads; with interpretation and report",
        code_type="cpt", value_tier="low", typical_setting="professional",
        applicable_settings=["professional","outpatient","inpatient"],
        risk_score=0.40, typical_units_max=1, requires_auth=False,
        specialty_typical="Cardiology / Primary Care", is_add_on=False, global_period_days=0,
        audit_notes="Extremely high-volume low-value service. Routine preoperative ECG is not separately billable when included in global surgical package. NCCI edits bundle ECG technical and professional components — billing 93005 (technical) and 93010 (professional) separately is appropriate only when facility and physician bill separately. Payers audit for frequency — multiple ECGs per encounter without clinical justification. Routine annual ECG in asymptomatic patients lacks USPSTF recommendation.",
        source_document="CPT 2025; CMS PFS FY2025; NCCI Edits",
        data_confidence=0.95, rule_certainty="guideline",
        dx_coverage=[
            dict(icd_code="I48.91",coverage_type="required",  rationale="Atrial fibrillation monitoring"),
            dict(icd_code="R07.9", coverage_type="supporting",rationale="Chest pain workup"),
            dict(icd_code="Z00.00",coverage_type="excluded",  rationale="Routine wellness ECG lacks coverage under most payer LCDs for asymptomatic patients"),
        ],
        valid_modifiers=[
            dict(modifier_code="26", ncci_override=False, payment_factor=None, notes="Professional component only — when physician interprets facility-performed ECG"),
            dict(modifier_code="TC", ncci_override=False, payment_factor=None, notes="Technical component only"),
        ],
    ),
    dict(
        code="93306", description="Echocardiography, transthoracic, real-time with image documentation; complete, with spectral Doppler and color flow Doppler echocardiography",
        code_type="cpt", value_tier="high", typical_setting="outpatient",
        applicable_settings=["professional","outpatient","inpatient"],
        risk_score=0.72, typical_units_max=1, requires_auth=True,
        specialty_typical="Cardiology", is_add_on=False, global_period_days=0,
        audit_notes="Highest-value cardiac imaging code; requires complete 2D echo with Doppler AND color flow. 93307 (without Doppler) and 93308 (limited) are lower-complexity alternatives — billing 93306 when documentation supports only limited study is upcoding. Frequency audits: repeat echo within 12 months for stable conditions without clinical change is a common denial. Prior authorization is standard for most commercial plans.",
        source_document="CPT 2025; CMS PFS FY2025; ACC Echo Appropriate Use Criteria",
        data_confidence=0.94, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="I50.9", coverage_type="required",  rationale="Heart failure evaluation — primary indication"),
            dict(icd_code="I48.91",coverage_type="supporting",rationale="AF rate control or cardioversion evaluation"),
            dict(icd_code="Z00.00",coverage_type="excluded",  rationale="Routine echo without cardiac symptoms or findings not covered"),
        ],
        valid_modifiers=[
            dict(modifier_code="26", ncci_override=False, payment_factor=None, notes="Professional interpretation only"),
            dict(modifier_code="TC", ncci_override=False, payment_factor=None, notes="Technical component only"),
        ],
    ),
    dict(
        code="93458", description="Catheter placement in coronary artery(s) for coronary angiography including intraprocedural injection(s) for left ventriculography",
        code_type="cpt", value_tier="high", typical_setting="outpatient",
        applicable_settings=["inpatient","outpatient"],
        risk_score=0.75, typical_units_max=1, requires_auth=True,
        specialty_typical="Interventional Cardiology", is_add_on=False, global_period_days=0,
        audit_notes="Diagnostic cardiac catheterization; significant utilization review exposure. ACC/AHA appropriate use criteria must support the indication — catheterization for low-risk stable chest pain without non-invasive testing is a common denial. When PCI (92928) is performed at same session, 93458 bundles into the interventional code per NCCI. Documentation must include procedure report, fluoroscopy time, contrast volume, and hemodynamic data.",
        source_document="CPT 2025; CMS PFS FY2025; ACC/AHA AUC for Coronary Revascularization; NCCI",
        data_confidence=0.93, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="I25.10",coverage_type="required",  rationale="Stable CAD with symptoms or positive stress test"),
            dict(icd_code="I21.9", coverage_type="supporting",rationale="Acute MI — STEMI/NSTEMI catheterization"),
            dict(icd_code="R07.9", coverage_type="excluded",  rationale="Chest pain alone without positive non-invasive testing is insufficient for cath authorization"),
        ],
        valid_modifiers=[
            dict(modifier_code="26", ncci_override=False, payment_factor=None, notes="Physician interpretation when separate from facility billing"),
        ],
    ),
    dict(
        code="92928", description="Percutaneous transcatheter placement of intracoronary stent(s), with coronary angioplasty when performed; major coronary artery or branch",
        code_type="cpt", value_tier="high", typical_setting="inpatient",
        applicable_settings=["inpatient","outpatient"],
        risk_score=0.70, typical_units_max=1, requires_auth=True,
        specialty_typical="Interventional Cardiology", is_add_on=False, global_period_days=0,
        audit_notes="PCI with stent placement; includes coronary angioplasty and angiography for treated vessel. Each additional vessel stented uses add-on code 92929. Drug-eluting vs bare metal stent uses HCPCS codes (C9600-C9607) in hospital OPPS billing. Appropriateness criteria require non-invasive test evidence of ischemia for elective PCI. Primary PCI for STEMI has different authorization pathway. Documentation must include vessel treated, lesion characteristics, and post-procedure TIMI flow.",
        source_document="CPT 2025; CMS OPPS; ACC/AHA PCI Guidelines; NCCI",
        data_confidence=0.93, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="I21.9", coverage_type="required",  rationale="Acute MI — primary indication for emergent PCI"),
            dict(icd_code="I25.10",coverage_type="supporting",rationale="Stable CAD with demonstrated ischemia"),
        ],
        valid_modifiers=[
            dict(modifier_code="LD", ncci_override=False, payment_factor=None, notes="Left anterior descending coronary artery"),
            dict(modifier_code="RC", ncci_override=False, payment_factor=None, notes="Right coronary artery"),
            dict(modifier_code="LC", ncci_override=False, payment_factor=None, notes="Left circumflex coronary artery"),
        ],
    ),
    dict(
        code="93798", description="Physician or other qualified health care professional services for outpatient cardiac rehabilitation; with continuous ECG monitoring",
        code_type="cpt", value_tier="moderate", typical_setting="outpatient",
        applicable_settings=["outpatient"],
        risk_score=0.62, typical_units_max=1, requires_auth=True,
        specialty_typical="Cardiology / Cardiac Rehab", is_add_on=False, global_period_days=0,
        audit_notes="Medicare covers up to 36 sessions of cardiac rehab (Phase II) with qualifying diagnosis (MI, CABG, stable angina, heart valve surgery, PTCA, heart transplant, or HFrEF). Each session must be 1 hour including exercise and education. Common audit finding: billing beyond covered sessions without medical review approval or for non-qualifying diagnoses. Documentation must include exercise prescription, patient response, and individualized treatment plan.",
        source_document="CPT 2025; CMS NCD 20.10; CMS Cardiac Rehab Coverage",
        data_confidence=0.91, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="I21.9", coverage_type="required",  rationale="Post-MI is a primary qualifying condition"),
            dict(icd_code="I50.9", coverage_type="supporting",rationale="HFrEF (EF ≤35%) added as qualifying condition in 2014"),
        ],
        valid_modifiers=[],
    ),
    # ── RADIOLOGY / IMAGING ────────────────────────────────────────────────
    dict(
        code="71046", description="Radiologic examination, chest; 2 views",
        code_type="cpt", value_tier="low", typical_setting="outpatient",
        applicable_settings=["professional","outpatient","inpatient","snf"],
        risk_score=0.38, typical_units_max=1, requires_auth=False,
        specialty_typical="Radiology / Emergency Medicine", is_add_on=False, global_period_days=0,
        audit_notes="Extremely high-volume; low individual risk but flags on frequency. Bundled into global surgical package if performed as pre-op. Cannot bill 71046 and 71045 (single view) on same date for same patient — use 71046 if 2 views obtained. Inpatient daily chest X-rays bundled into DRG payment and not separately payable to professional. Pre-authorization not typically required but medical necessity needed for repeated imaging.",
        source_document="CPT 2025; CMS PFS FY2025; NCCI Edits",
        data_confidence=0.96, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="R07.9", coverage_type="supporting",rationale="Chest pain is standard indication"),
            dict(icd_code="J18.9", coverage_type="supporting",rationale="Pneumonia confirmation or follow-up"),
            dict(icd_code="J44.1", coverage_type="supporting",rationale="COPD exacerbation"),
        ],
        valid_modifiers=[
            dict(modifier_code="26", ncci_override=False, payment_factor=None, notes="Professional component — radiologist interpretation"),
            dict(modifier_code="TC", ncci_override=False, payment_factor=None, notes="Technical component — facility"),
        ],
    ),
    dict(
        code="70553", description="Magnetic resonance imaging, brain; without contrast material(s), followed by contrast material(s) and further sequences",
        code_type="cpt", value_tier="high", typical_setting="outpatient",
        applicable_settings=["professional","outpatient","inpatient"],
        risk_score=0.65, typical_units_max=1, requires_auth=True,
        specialty_typical="Radiology / Neurology", is_add_on=False, global_period_days=0,
        audit_notes="High-value imaging requiring prior authorization. With and without contrast (70553) vs without only (70551) vs with only (70552) — billing with-contrast when only without was performed is upcoding. Documentation must justify need for contrast (known/suspected neoplasm, post-surgical follow-up, infectious process). Contrast administration must be documented in radiology report including type and volume.",
        source_document="CPT 2025; CMS PFS FY2025; ACR Appropriateness Criteria",
        data_confidence=0.93, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="I63.9", coverage_type="required",  rationale="Cerebral infarction — acute stroke MRI protocol"),
            dict(icd_code="G35",   coverage_type="supporting",rationale="MS lesion monitoring or new symptom workup"),
            dict(icd_code="G43.909",coverage_type="excluded", rationale="Routine migraine without new neurological features generally does not require brain MRI per appropriateness criteria"),
        ],
        valid_modifiers=[
            dict(modifier_code="26", ncci_override=False, payment_factor=None, notes="Professional interpretation"),
            dict(modifier_code="TC", ncci_override=False, payment_factor=None, notes="Technical component"),
        ],
    ),
    dict(
        code="72148", description="Magnetic resonance imaging, spinal canal and contents, lumbar; without contrast material",
        code_type="cpt", value_tier="high", typical_setting="outpatient",
        applicable_settings=["professional","outpatient"],
        risk_score=0.70, typical_units_max=1, requires_auth=True,
        specialty_typical="Radiology / Orthopedic Surgery", is_add_on=False, global_period_days=0,
        audit_notes="High-volume, high-audit imaging. Most payer LCDs require 4–6 weeks of conservative treatment failure before approving lumbar MRI for non-emergency back pain. Red flag symptoms (cauda equina, progressive neurological deficit, malignancy, infection, fracture) support immediate authorization. CMS has specifically targeted spine imaging utilization. M54.5 (retired FY2023) on a claim with DOS ≥2022-10-01 should fail code validity check.",
        source_document="CPT 2025; CMS PFS FY2025; ACR Appropriateness Criteria; CMS LCD L34010",
        data_confidence=0.94, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="M54.50",coverage_type="supporting",rationale="Low back pain — requires conservative treatment failure documentation"),
            dict(icd_code="G82.50",coverage_type="required",  rationale="Acute neurological deficit requires immediate imaging"),
            dict(icd_code="M54.5", coverage_type="excluded",  rationale="Retired code (FY2023) — claim should fail code validity check"),
        ],
        valid_modifiers=[
            dict(modifier_code="26", ncci_override=False, payment_factor=None, notes="Professional interpretation"),
            dict(modifier_code="TC", ncci_override=False, payment_factor=None, notes="Technical component"),
        ],
    ),
    dict(
        code="77067", description="Screening mammography, bilateral (2-view study of each breast)",
        code_type="cpt", value_tier="moderate", typical_setting="outpatient",
        applicable_settings=["professional","outpatient"],
        risk_score=0.50, typical_units_max=1, requires_auth=False,
        specialty_typical="Radiology", is_add_on=False, global_period_days=0,
        audit_notes="Annual screening mammography. Medicare covers once per year. Bilateral (77067) vs unilateral (77066) — bilateral is standard; unilateral post-mastectomy should use 77066. When a screening mammogram identifies a finding requiring diagnostic workup on the same date, 77065/77066 (diagnostic) replaces 77067 — they cannot be billed together. 3D tomosynthesis add-on code 77063 requires separate documentation of medical necessity.",
        source_document="CPT 2025; CMS PFS FY2025; USPSTF Mammography Guideline 2024",
        data_confidence=0.95, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="Z12.31",coverage_type="required",  rationale="Screening mammography indication code"),
            dict(icd_code="Z80.3", coverage_type="supporting",rationale="Family history of breast cancer supports earlier/more frequent screening"),
        ],
        valid_modifiers=[
            dict(modifier_code="GG", ncci_override=False, payment_factor=None, notes="Performance and payment of screening and diagnostic mammogram same patient same day"),
        ],
    ),
    dict(
        code="78816", description="Positron emission tomography (PET) imaging; whole body",
        code_type="cpt", value_tier="high", typical_setting="outpatient",
        applicable_settings=["outpatient"],
        risk_score=0.75, typical_units_max=1, requires_auth=True,
        specialty_typical="Radiology / Nuclear Medicine", is_add_on=False, global_period_days=0,
        audit_notes="High-cost imaging with strict CMS NCD coverage criteria (NCD 220.6.19); covered for initial staging and subsequent treatment monitoring of specific malignancies and for solitary pulmonary nodule evaluation. Coverage for Alzheimer's diagnosis (amyloid PET) has separate NCD 220.6.20. Denial rate is high for off-label indications. Documentation must specify the covered indication and clinical context.",
        source_document="CPT 2025; CMS NCD 220.6.19; CMS NCD 220.6.20",
        data_confidence=0.92, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="C34.90",coverage_type="required",  rationale="Lung malignancy — covered for initial staging and restaging"),
            dict(icd_code="Z12.11",coverage_type="excluded",  rationale="Screening indication — PET not covered for cancer screening"),
        ],
        valid_modifiers=[
            dict(modifier_code="26", ncci_override=False, payment_factor=None, notes="Professional interpretation"),
            dict(modifier_code="TC", ncci_override=False, payment_factor=None, notes="Technical component"),
        ],
    ),
    # ── PHYSICAL THERAPY ───────────────────────────────────────────────────
    dict(
        code="97110", description="Therapeutic procedure, 1 or more areas, each 15 minutes; therapeutic exercises to develop strength and endurance, range of motion and flexibility",
        code_type="cpt", value_tier="moderate", typical_setting="outpatient",
        applicable_settings=["professional","outpatient","snf","home_health"],
        risk_score=0.65, typical_units_max=4, requires_auth=True,
        specialty_typical="Physical Therapy", is_add_on=False, global_period_days=0,
        audit_notes="Highest-volume physical therapy code; each unit = 15 minutes of direct one-on-one care. The 8-minute rule applies — a service must be provided for at least 8 minutes to bill one unit; 23+ minutes for 2 units. Timed and untimed code combinations must follow CMS counting rules. Requires a documented plan of care with measurable functional goals. Common audit finding: billing 4 units (60 min) of 97110 while also billing other timed codes creating total time inconsistencies. KX modifier required when Medicare therapy cap thresholds are met.",
        source_document="CPT 2025; CMS PFS FY2025; CMS 8-Minute Rule; CMS Therapy Cap Policy",
        data_confidence=0.95, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="M17.11", coverage_type="supporting",rationale="Post-op knee rehab or conservative OA management"),
            dict(icd_code="I63.9",  coverage_type="supporting",rationale="Post-stroke motor rehabilitation"),
            dict(icd_code="S72.001A",coverage_type="supporting",rationale="Post-hip fracture gait and strength training"),
        ],
        valid_modifiers=[
            dict(modifier_code="KX", ncci_override=False, payment_factor=1.0, notes="Medicare: medical necessity supports services above therapy cap threshold"),
            dict(modifier_code="GP", ncci_override=False, payment_factor=1.0, notes="Physical therapy plan of care"),
            dict(modifier_code="59", ncci_override=True,  payment_factor=1.0, notes="Distinct service when multiple PT codes billed same day"),
        ],
    ),
    dict(
        code="97530", description="Therapeutic activities, direct (one-on-one) patient contact by the provider, each 15 minutes",
        code_type="cpt", value_tier="moderate", typical_setting="outpatient",
        applicable_settings=["professional","outpatient","snf","home_health"],
        risk_score=0.68, typical_units_max=4, requires_auth=True,
        specialty_typical="Physical Therapy / Occupational Therapy", is_add_on=False, global_period_days=0,
        audit_notes="Functional activity training code; distinct from 97110 in that it involves dynamic, task-oriented activities simulating real-world functions (ADLs, transfers, balance). NCCI bundles 97530 with 97110 when billed same day — requires modifier 59 and documentation of distinct activities. Each 15-minute unit requires direct therapist contact. Commonly overbilled in SNF settings; OIG has targeted SNF therapy upcoding involving 97530 billed without functional documentation.",
        source_document="CPT 2025; CMS PFS FY2025; NCCI; OIG SNF Therapy Audit Reports",
        data_confidence=0.93, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="I63.9",coverage_type="supporting",rationale="Post-stroke ADL retraining"),
            dict(icd_code="G20",  coverage_type="supporting",rationale="Parkinson's functional mobility training"),
        ],
        valid_modifiers=[
            dict(modifier_code="59", ncci_override=True,  payment_factor=1.0, notes="Distinct service from 97110 when billed same day"),
            dict(modifier_code="KX", ncci_override=False, payment_factor=1.0, notes="Above therapy cap with documented medical necessity"),
            dict(modifier_code="GO", ncci_override=False, payment_factor=1.0, notes="Occupational therapy plan of care"),
        ],
    ),
    dict(
        code="97012", description="Application of a modality to 1 or more areas; traction, mechanical",
        code_type="cpt", value_tier="low", typical_setting="outpatient",
        applicable_settings=["professional","outpatient"],
        risk_score=0.55, typical_units_max=1, requires_auth=False,
        specialty_typical="Physical Therapy / Chiropractic", is_add_on=False, global_period_days=0,
        audit_notes="Untimed code — billed once per day regardless of duration. Must not be billed for constant attendance (97016 or 97018). Cannot be billed concurrently with 97110 or 97530 if traction is the only service. Medicare and many commercial plans have limited coverage for passive modalities like mechanical traction; documentation must show specific therapeutic indication. Common overbilling: billing modalities for time-filler when active therapy time was insufficient.",
        source_document="CPT 2025; CMS PFS FY2025",
        data_confidence=0.88, rule_certainty="guideline",
        dx_coverage=[
            dict(icd_code="M54.50",coverage_type="supporting",rationale="Low back pain with radiculopathy"),
            dict(icd_code="M54.2", coverage_type="supporting",rationale="Cervicalgia with nerve root compression"),
        ],
        valid_modifiers=[
            dict(modifier_code="GP", ncci_override=False, payment_factor=1.0, notes="PT plan of care"),
        ],
    ),
    dict(
        code="97161", description="Physical therapy evaluation: low complexity",
        code_type="cpt", value_tier="moderate", typical_setting="outpatient",
        applicable_settings=["professional","outpatient","snf","home_health"],
        risk_score=0.50, typical_units_max=1, requires_auth=False,
        specialty_typical="Physical Therapy", is_add_on=False, global_period_days=0,
        audit_notes="PT evaluation replaces older 97001 code; complexity determined by clinical presentation (97161 low, 97162 moderate, 97163 high). Low complexity requires 1 stable condition, no comorbidities affecting PT, and straightforward clinical decision making. Common error: billing 97163 (high complexity) for straightforward musculoskeletal presentations. Re-evaluation (97164) is separately billable when significant change in clinical status occurs.",
        source_document="CPT 2025; CMS PFS FY2025; APTA Documentation Guidelines",
        data_confidence=0.93, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="M54.50",coverage_type="supporting",rationale="Low back pain evaluation — low complexity typical"),
            dict(icd_code="M17.11",coverage_type="supporting",rationale="Post-TKA PT evaluation"),
        ],
        valid_modifiers=[
            dict(modifier_code="GP", ncci_override=False, payment_factor=1.0, notes="PT plan of care"),
        ],
    ),
    # ── BEHAVIORAL HEALTH ──────────────────────────────────────────────────
    dict(
        code="90837", description="Psychotherapy, 60 minutes with patient",
        code_type="cpt", value_tier="moderate", typical_setting="professional",
        applicable_settings=["professional","outpatient"],
        risk_score=0.70, typical_units_max=1, requires_auth=True,
        specialty_typical="Psychiatry / Psychology / LCSW", is_add_on=False, global_period_days=0,
        audit_notes="60-minute psychotherapy; must be 53+ minutes to bill 90837 (use 90834 for 38–52 minutes, 90832 for 16–37 minutes). Time spent on administrative activities does not count. MHPAEA requires parity with medical/surgical. Telehealth psychotherapy is high-audit post-PHE; audio-only requires FQ modifier for Medicare. Documentation must include mental status, treatment plan, interventions used, and patient response.",
        source_document="CPT 2025; CMS PFS FY2025; MHPAEA; APA Documentation Standards",
        data_confidence=0.94, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="F32.9",coverage_type="required",  rationale="Major depression — primary psychotherapy indication"),
            dict(icd_code="F41.1",coverage_type="supporting",rationale="GAD psychotherapy"),
            dict(icd_code="Z00.00",coverage_type="excluded", rationale="Wellness visit — psychotherapy not billable without psychiatric diagnosis"),
        ],
        valid_modifiers=[
            dict(modifier_code="95", ncci_override=False, payment_factor=1.0, notes="Synchronous telehealth"),
            dict(modifier_code="FQ", ncci_override=False, payment_factor=1.0, notes="Audio-only Medicare telehealth"),
        ],
    ),
    dict(
        code="90847", description="Family psychotherapy (conjoint psychotherapy) (with patient present), 50 minutes",
        code_type="cpt", value_tier="moderate", typical_setting="professional",
        applicable_settings=["professional","outpatient"],
        risk_score=0.62, typical_units_max=1, requires_auth=True,
        specialty_typical="Psychiatry / Psychology / LCSW", is_add_on=False, global_period_days=0,
        audit_notes="Family therapy with patient present; 90846 is family therapy without patient. Cannot bill 90847 and individual psychotherapy on same day for same patient unless clearly documented as distinct. Must have an identified patient with a diagnosable mental health condition. 50-minute minimum required. Payers audit for same-day combination billing of individual and family therapy.",
        source_document="CPT 2025; CMS PFS FY2025; APA Documentation Standards",
        data_confidence=0.91, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="F32.9",coverage_type="required",rationale="Identified patient's primary diagnosis drives coverage"),
        ],
        valid_modifiers=[
            dict(modifier_code="95", ncci_override=False, payment_factor=1.0, notes="Telehealth"),
        ],
    ),
    dict(
        code="90853", description="Group psychotherapy (other than of a multiple-family group)",
        code_type="cpt", value_tier="low", typical_setting="outpatient",
        applicable_settings=["professional","outpatient"],
        risk_score=0.75, typical_units_max=1, requires_auth=True,
        specialty_typical="Psychiatry / Psychology / LCSW", is_add_on=False, global_period_days=0,
        audit_notes="Group therapy; 2–12 patients per session is standard. Payers and OIG have heavily audited group therapy — high-volume fraud schemes involve billing individual therapy rates for group sessions, or billing for sessions that did not occur. Documentation must include group size, therapist name, session date and duration, and a brief note for each patient present. Group sessions billed same day as individual therapy require documentation that both occurred as distinct services.",
        source_document="CPT 2025; CMS PFS FY2025; OIG BH Fraud Work Plan; SAMHSA Guidelines",
        data_confidence=0.93, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="F32.9",coverage_type="supporting",rationale="Depression group therapy"),
            dict(icd_code="F41.1",coverage_type="supporting",rationale="Anxiety group therapy"),
        ],
        valid_modifiers=[
            dict(modifier_code="HQ", ncci_override=False, payment_factor=None, notes="Group setting — required by some Medicaid programs"),
        ],
    ),
    # ── SLEEP STUDIES ──────────────────────────────────────────────────────
    dict(
        code="95810", description="Polysomnography; age 6 years or older, sleep staging with 4 or more additional parameters of sleep, attended by a technologist",
        code_type="cpt", value_tier="high", typical_setting="sleep_inlab",
        applicable_settings=["sleep_inlab"],
        risk_score=0.78, typical_units_max=1, requires_auth=True,
        specialty_typical="Sleep Medicine / Pulmonology", is_add_on=False, global_period_days=0,
        audit_notes="Full attended in-lab polysomnography; requires sleep staging + ≥4 additional parameters. Technologist must be present throughout. CMS LCD L33718 requires documented clinical evaluation supporting OSA or other sleep disorder. If AHI ≥15 on diagnostic PSG portion, split-night titration may be performed same night (billed as 95811 not 95810). Comorbidities requiring in-lab testing (CHF, COPD, neuromuscular disease) must be documented to justify in-lab over HST.",
        source_document="CPT 2025; CMS PFS FY2025; CMS LCD L33718; AASM PSG Standards",
        data_confidence=0.95, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="G47.33", coverage_type="required",  rationale="OSA evaluation is primary indication for PSG"),
            dict(icd_code="G47.52", coverage_type="supporting",rationale="RBD requires in-lab video PSG — HST not appropriate"),
            dict(icd_code="G47.411",coverage_type="supporting",rationale="Narcolepsy evaluation requires PSG + MSLT"),
        ],
        valid_modifiers=[
            dict(modifier_code="52", ncci_override=False, payment_factor=None, notes="Reduced service — study terminated early or incomplete parameters"),
        ],
    ),
    dict(
        code="95811", description="Polysomnography; age 6 years or older, sleep staging with 4 or more additional parameters of sleep, with initiation of CPAP therapy or bilevel ventilation, attended by a technologist",
        code_type="cpt", value_tier="high", typical_setting="sleep_inlab",
        applicable_settings=["sleep_inlab"],
        risk_score=0.75, typical_units_max=1, requires_auth=True,
        specialty_typical="Sleep Medicine / Pulmonology", is_add_on=False, global_period_days=0,
        audit_notes="CPAP/BiPAP titration PSG; requires prior diagnostic PSG documenting AHI ≥5 for coverage — titration without prior diagnosis is a claim integrity flag. Split-night protocol requires AHI ≥15 on diagnostic portion per AASM standards and must be documented in the study report. Cannot bill 95810 and 95811 on same night unless split-night is documented. BiPAP titration for complex sleep apnea uses 95811 with documentation of ASV or BiPAP ST indication.",
        source_document="CPT 2025; CMS LCD L33718; AASM Split-Night Protocol",
        data_confidence=0.94, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="G47.33",coverage_type="required",  rationale="Confirmed OSA requiring CPAP titration"),
            dict(icd_code="G47.37",coverage_type="supporting",rationale="Complex sleep apnea requiring in-lab ASV titration"),
        ],
        valid_modifiers=[
            dict(modifier_code="52", ncci_override=False, payment_factor=None, notes="Incomplete titration study"),
        ],
    ),
    dict(
        code="95806", description="Sleep study, unattended, simultaneous recording of heart rate, oxygen saturation, respiratory airflow, and respiratory effort",
        code_type="cpt", value_tier="moderate", typical_setting="sleep_home",
        applicable_settings=["sleep_home"],
        risk_score=0.72, typical_units_max=1, requires_auth=True,
        specialty_typical="Sleep Medicine / Pulmonology / Primary Care", is_add_on=False, global_period_days=0,
        audit_notes="Type III home sleep test — the most commonly billed HST code. Appropriate only for high pre-test probability OSA without significant comorbidities (CHF, COPD, neuromuscular disease). CMS LCD L33718 requires physician order, clinical evaluation documentation, and absence of HST-disqualifying comorbidities. Result must be interpreted by a board-eligible/certified sleep physician. Patients should not perform HST more than twice for the same diagnostic episode.",
        source_document="CPT 2025; CMS LCD L33718; AASM HST Guidelines",
        data_confidence=0.94, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="G47.30",coverage_type="required",  rationale="Suspected sleep apnea — pre-diagnosis"),
            dict(icd_code="I50.32",coverage_type="excluded",  rationale="CHF is a HST contraindication — in-lab PSG required"),
            dict(icd_code="J44.9", coverage_type="excluded",  rationale="Significant COPD is a HST contraindication per LCD"),
        ],
        valid_modifiers=[
            dict(modifier_code="52", ncci_override=False, payment_factor=None, notes="Incomplete study — insufficient recording time"),
        ],
    ),
    dict(
        code="95805", description="Multiple sleep latency or maintenance of wakefulness testing, recording, analysis and interpretation of physiological measurements of sleep during multiple trials",
        code_type="cpt", value_tier="high", typical_setting="sleep_inlab",
        applicable_settings=["sleep_inlab"],
        risk_score=0.80, typical_units_max=1, requires_auth=True,
        specialty_typical="Sleep Medicine / Neurology", is_add_on=False, global_period_days=0,
        audit_notes="MSLT (narcolepsy/idiopathic hypersomnia diagnosis) and MWT (fitness for duty/treatment response) — distinct clinical uses require different documentation. MSLT must be preceded by an overnight PSG (95810) on the same or preceding night per AASM standards — billing 95805 without a preceding PSG is a clinical and billing error. Mean sleep latency and SOREMP count must be reported. Prior to MSLT, patients must discontinue REM-suppressing medications for ≥2 weeks per AASM guidelines.",
        source_document="CPT 2025; CMS PFS FY2025; CMS LCD L34028; AASM MSLT Protocol",
        data_confidence=0.93, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="G47.411",coverage_type="required",  rationale="Narcolepsy with cataplexy — MSLT required for diagnosis"),
            dict(icd_code="G47.419",coverage_type="supporting",rationale="Narcolepsy without cataplexy"),
            dict(icd_code="G47.11", coverage_type="supporting",rationale="Idiopathic hypersomnia — MSLT required"),
        ],
        valid_modifiers=[],
    ),
    # ── HCPCS / DME ────────────────────────────────────────────────────────
    dict(
        code="E0601", description="Continuous positive airway pressure (CPAP) device",
        code_type="hcpcs", value_tier="high", typical_setting="dme",
        applicable_settings=["dme","home_health"],
        risk_score=0.82, typical_units_max=1, requires_auth=True,
        specialty_typical="DMEPOS Supplier", is_add_on=False, global_period_days=0,
        audit_notes="Highest-audit DMEPOS code; CMS requires: (1) positive diagnostic test (PSG or HST) showing AHI ≥5 with symptoms or AHI ≥15 without symptoms, (2) written physician order, (3) compliance monitoring at 31–90 days showing ≥4 hours/night for ≥70% of nights in 30-day period. If compliance is not met, CPAP rental ceases. Compliance download from device is mandatory for continued coverage. RAC and OIG audits routinely find significant overpayments when compliance criteria are not documented. CPAP supplies (A7027–A7039) have their own frequency limits.",
        source_document="HCPCS 2025; CMS LCD L33718; CMS DMEPOS Policy; OIG CPAP Audit Reports",
        data_confidence=0.97, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="G47.33",coverage_type="required",  rationale="Confirmed OSA — mandatory for CPAP coverage"),
            dict(icd_code="G47.31",coverage_type="excluded",  rationale="Central sleep apnea — CPAP alone not appropriate; may worsen CSA"),
        ],
        valid_modifiers=[
            dict(modifier_code="KX", ncci_override=False, payment_factor=1.0, notes="Documentation supports coverage criteria — required on CPAP claims"),
            dict(modifier_code="NU", ncci_override=False, payment_factor=None, notes="New equipment purchase"),
            dict(modifier_code="RR", ncci_override=False, payment_factor=None, notes="Rental"),
        ],
    ),
    dict(
        code="E0471", description="Respiratory assist device, bi-level pressure capability, without backup rate feature, used with noninvasive interface",
        code_type="hcpcs", value_tier="high", typical_setting="dme",
        applicable_settings=["dme","home_health"],
        risk_score=0.80, typical_units_max=1, requires_auth=True,
        specialty_typical="DMEPOS Supplier / Pulmonology", is_add_on=False, global_period_days=0,
        audit_notes="BiPAP without backup rate; covered for OSA failing CPAP, obesity hypoventilation syndrome, or COPD-OSA overlap per CMS LCD. Must have prior CPAP trial with documented failure. Compliance monitoring requirements identical to CPAP (E0601). Prescribing BiPAP for simple OSA without documented CPAP failure is a frequent audit finding. ASV (E0601 device code) has specific contraindication for systolic HF with CSA.",
        source_document="HCPCS 2025; CMS LCD L33718; CMS LCD L33786 (Respiratory Assist Devices)",
        data_confidence=0.93, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="G47.33",coverage_type="supporting",rationale="OSA with documented CPAP intolerance/failure"),
            dict(icd_code="J44.9", coverage_type="supporting",rationale="COPD-OSA overlap syndrome"),
            dict(icd_code="I50.32",coverage_type="excluded",  rationale="ASV is contraindicated in systolic HF with CSA — flag if E0601 ASV billed with this diagnosis"),
        ],
        valid_modifiers=[
            dict(modifier_code="KX", ncci_override=False, payment_factor=1.0, notes="Required — CPAP failure documented in medical record"),
        ],
    ),
    dict(
        code="L3000", description="Foot insert, removable, molded to patient model, UCB type, Berkeley shell, each",
        code_type="hcpcs", value_tier="low", typical_setting="dme",
        applicable_settings=["dme"],
        risk_score=0.60, typical_units_max=2, requires_auth=False,
        specialty_typical="Podiatry / Orthotics", is_add_on=False, global_period_days=0,
        audit_notes="Custom molded foot orthotic; distinguished from prefabricated orthotics (A5512, A5513). Custom orthotics require a cast or mold of the patient's foot — billing L3000 for a prefabricated device is fraud. For diabetic patients, therapeutic shoe benefits (A5500) have separate coverage under Medicare's DSHF benefit. Podiatry practices have been targeted by OIG for billing custom orthotics without documentation of medical necessity or casting.",
        source_document="HCPCS 2025; CMS DMEPOS Fee Schedule; CMS LCD L33369",
        data_confidence=0.88, rule_certainty="guideline",
        dx_coverage=[
            dict(icd_code="E11.621",coverage_type="supporting",rationale="Diabetic foot complications support orthotic medical necessity"),
            dict(icd_code="M17.11", coverage_type="supporting",rationale="Knee OA with biomechanical foot issues"),
        ],
        valid_modifiers=[
            dict(modifier_code="RT", ncci_override=False, payment_factor=1.0, notes="Right foot"),
            dict(modifier_code="LT", ncci_override=False, payment_factor=1.0, notes="Left foot"),
        ],
    ),
    dict(
        code="K0001", description="Standard manual wheelchair",
        code_type="hcpcs", value_tier="moderate", typical_setting="dme",
        applicable_settings=["dme","snf","home_health"],
        risk_score=0.65, typical_units_max=1, requires_auth=True,
        specialty_typical="DMEPOS Supplier", is_add_on=False, global_period_days=0,
        audit_notes="Manual wheelchair coverage requires documented mobility limitation preventing community ambulation and a face-to-face examination by treating physician or PT/OT. Higher-complexity wheelchairs (K0004-K0008, power wheelchairs K0800+) require additional documentation and PT/OT assessment. Common audit finding: billing power wheelchair when standard manual is medically appropriate. SNF consolidated billing bundles wheelchair into Part A payment — DME billing during SNF Part A stay is inappropriate.",
        source_document="HCPCS 2025; CMS LCD L33702; CMS DMEPOS; OIG Wheelchair Audit",
        data_confidence=0.90, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="G82.50",coverage_type="required",  rationale="Quadriplegia — power wheelchair clinical necessity"),
            dict(icd_code="I63.9", coverage_type="supporting",rationale="Post-stroke mobility limitation"),
        ],
        valid_modifiers=[
            dict(modifier_code="KX", ncci_override=False, payment_factor=1.0, notes="Medical necessity criteria documented in file"),
            dict(modifier_code="NU", ncci_override=False, payment_factor=None, notes="New equipment purchase"),
        ],
    ),
    dict(
        code="A9270", description="Non-covered item or service",
        code_type="hcpcs", value_tier="low", typical_setting="dme",
        applicable_settings=["dme","professional","outpatient"],
        risk_score=0.30, typical_units_max=1, requires_auth=False,
        specialty_typical="DMEPOS Supplier", is_add_on=False, global_period_days=0,
        audit_notes="Catch-all non-covered code used for items Medicare/payer will not cover. Required in conjunction with an Advance Beneficiary Notice (ABN) when patient is being billed directly. Commonly used for premium IOL upgrades, non-covered DME accessories, and cosmetic items. Providers must issue ABN before providing service when non-coverage is anticipated — billing A9270 without an ABN is a compliance violation. Should not appear on claims submitted to payer for reimbursement without corresponding ABN documentation.",
        source_document="HCPCS 2025; CMS ABN Requirements; CMS Pub 100-04 Ch. 30",
        data_confidence=0.88, rule_certainty="mandatory",
        dx_coverage=[],
        valid_modifiers=[
            dict(modifier_code="GA", ncci_override=False, payment_factor=None, notes="ABN on file — required when billing non-covered item"),
            dict(modifier_code="GX", ncci_override=False, payment_factor=None, notes="Notice given — voluntary ABN for items expected non-covered"),
        ],
    ),
    dict(
        code="G0283", description="Electrical stimulation (unattended), to one or more areas for indication(s) other than wound care, as part of a physical therapy plan of care",
        code_type="hcpcs", value_tier="low", typical_setting="outpatient",
        applicable_settings=["professional","outpatient","snf"],
        risk_score=0.55, typical_units_max=1, requires_auth=False,
        specialty_typical="Physical Therapy", is_add_on=False, global_period_days=0,
        audit_notes="Unattended e-stim used in PT for pain management or muscle re-education; must be part of a documented PT plan of care. NCCI bundles G0283 with 97032 (attended e-stim) — cannot bill both same day same area. Medicare has limited coverage for many electrical stimulation modalities. SNF consolidated billing includes modalities like G0283 in the Part A per diem.",
        source_document="HCPCS 2025; CMS PFS FY2025; NCCI; CMS LCD for E-Stim",
        data_confidence=0.88, rule_certainty="guideline",
        dx_coverage=[
            dict(icd_code="M54.50",coverage_type="supporting",rationale="Low back pain — e-stim as adjunct to PT"),
            dict(icd_code="M17.11",coverage_type="supporting",rationale="Knee OA pain management during PT"),
        ],
        valid_modifiers=[
            dict(modifier_code="GP", ncci_override=False, payment_factor=1.0, notes="PT plan of care"),
        ],
    ),
    dict(
        code="J0585", description="Injection, onabotulinumtoxinA, 1 unit",
        code_type="hcpcs", value_tier="high", typical_setting="professional",
        applicable_settings=["professional","outpatient"],
        risk_score=0.82, typical_units_max=200, requires_auth=True,
        specialty_typical="Neurology / Dermatology / Urology", is_add_on=False, global_period_days=0,
        audit_notes="Botulinum toxin A (Botox); units billed must match dosage documented in procedure note exactly — billing 200 units when 100 units were administered is a common fraud pattern. Prior authorization required for all CMS-covered indications (chronic migraine G43.709, cervical dystonia G24.3, spasticity, hyperhidrosis, overactive bladder). Cosmetic use is non-covered and requires ABN. Three different Botulinum toxin products have different unit conversion ratios — mixing up product codes is a billing error. Payers audit for frequency compliance (chronic migraine: every 12 weeks minimum interval).",
        source_document="HCPCS 2025; CMS PFS FY2025; CMS LCD L33449; AAN Migraine Guidelines",
        data_confidence=0.94, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="G43.909",coverage_type="excluded",  rationale="Unspecified migraine — must specify chronic migraine (G43.709) for coverage"),
        ],
        valid_modifiers=[
            dict(modifier_code="JW", ncci_override=False, payment_factor=None, notes="Drug amount discarded — required for wasted single-dose vial portion"),
        ],
    ),
    dict(
        code="Q4131", description="Apligraf, per square centimeter",
        code_type="hcpcs", value_tier="high", typical_setting="outpatient",
        applicable_settings=["outpatient","asc","home_health"],
        risk_score=0.85, typical_units_max=100, requires_auth=True,
        specialty_typical="Wound Care / Dermatology / Podiatry", is_add_on=False, global_period_days=0,
        audit_notes="Bioengineered skin substitute; among the highest-cost per-claim HCPCS codes in outpatient wound care. CMS coverage requires documented chronic wound (DFU or venous leg ulcer) unresponsive to ≥4 weeks of standard wound care. Units billed must match documented wound surface area — billing more units than the measured wound cm² is fraud. OIG and MAC auditors have found significant overbilling through phantom billing, upcoding to higher-cost products, and billing without documentation of standard care failure. Application CPT (15271-15278) billed concurrently.",
        source_document="HCPCS 2025; CMS OPPS; CMS LCD L39012 (Skin Substitutes); OIG Skin Sub Fraud Alert",
        data_confidence=0.91, rule_certainty="mandatory",
        dx_coverage=[
            dict(icd_code="E11.621",coverage_type="required",  rationale="Diabetic foot ulcer — primary indication"),
            dict(icd_code="L89.90", coverage_type="excluded",  rationale="Pressure ulcers are not covered by Q4131 per current CMS LCD"),
        ],
        valid_modifiers=[
            dict(modifier_code="Q7", ncci_override=False, payment_factor=None, notes="One Class A finding — lower extremity wound qualifier"),
        ],
    ),
]

# ── Minimal ICD codes referenced in dx_coverage not yet in DB ─────────────────
MISSING_ICD = [
    ("K63.5",  "Polyp of colon",                                          "icd10_cm", "moderate"),
    ("M23.200","Derangement of unspecified meniscus due to old tear or injury", "icd10_cm", "moderate"),
    ("H25.11", "Age-related nuclear cataract, right eye",                  "icd10_cm", "moderate"),
    ("H26.9",  "Unspecified cataract",                                     "icd10_cm", "moderate"),
    ("Z80.3",  "Family history of malignant neoplasm of breast",           "icd10_cm", "low"),
    ("G47.419","Narcolepsy without cataplexy",                             "icd10_cm", "high"),
    ("G47.11", "Idiopathic hypersomnia with long sleep time",              "icd10_cm", "moderate"),
    ("M17.0",  "Bilateral primary osteoarthritis of knee",                 "icd10_cm", "moderate"),
    ("M23.200","Derangement of unspecified lateral meniscus due to old tear or injury", "icd10_cm", "moderate"),
    ("G24.3",  "Spasmodic torticollis",                                    "icd10_cm", "moderate"),
]


def run(db_path: str = DB_PATH) -> int:
    conn = sqlite3.connect(db_path)
    cpt_inserted = cpt_updated = dx_inserted = mod_map_inserted = mod_inserted = 0
    try:
        # 1. Insert missing modifier codes (minimal records)
        for row in NEW_MODIFIERS:
            (code, desc, mtype, applies, impact, factor, ncci, req_doc,
             risk, notes, src_auth, src_doc) = row
            conn.execute(
                "INSERT OR IGNORE INTO modifier_codes "
                "(modifier_code_id, code, description, modifier_type, applies_to, "
                "payment_impact, payment_factor, ncci_override, requires_documentation, "
                "audit_risk_score, audit_notes, source_authority, source_document, "
                "data_confidence, data_confidence_notes, rule_certainty, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (str(uuid4()), code, desc, mtype, applies,
                 impact, factor, int(ncci), int(req_doc), risk, notes,
                 src_auth, src_doc,
                 0.90, "Structured output from Claude (claude.ai) validated against CPT 2025",
                 "mandatory", NOW, NOW),
            )
            if conn.execute("SELECT changes()").fetchone()[0]:
                mod_inserted += 1

        # 2. Insert minimal ICD codes referenced in dx_coverage but not in DB
        for code, desc, ctype, tier in MISSING_ICD:
            conn.execute(
                "INSERT OR IGNORE INTO icd_codes "
                "(icd_code_id, code, description, code_type, value_tier, "
                "typical_setting, valid_as_primary_dx, "
                "source_authority, source_document, "
                "data_confidence, rule_certainty, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (str(uuid4()), code, desc, ctype, tier,
                 "both", 1,
                 "CMS", "ICD-10-CM 2025",
                 0.85, "mandatory", NOW, NOW),
            )

        # 3. Upsert CPT/HCPCS codes
        for entry in CODES:
            code = entry["code"]
            settings_json = json.dumps(entry.get("applicable_settings", []))

            conn.execute(
                "INSERT OR IGNORE INTO cpt_codes "
                "(cpt_code_id, code, description, code_type, value_tier, "
                "typical_setting, applicable_settings, "
                "risk_score, typical_units_max, requires_auth, specialty_typical, "
                "is_add_on, global_period_days, audit_notes, "
                "source_authority, source_document, source_url, last_reviewed_at, "
                "data_confidence, data_confidence_notes, rule_certainty, "
                "created_at, updated_at) VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()), code, entry["description"], entry["code_type"],
                    entry["value_tier"], entry["typical_setting"], settings_json,
                    entry["risk_score"], entry["typical_units_max"], int(entry["requires_auth"]),
                    entry["specialty_typical"], int(entry["is_add_on"]),
                    entry["global_period_days"], entry.get("audit_notes"),
                    "AMA" if entry["code_type"] == "cpt" else "CMS",
                    entry.get("source_document", "CPT 2025"),
                    "https://www.ama-assn.org/practice-management/cpt",
                    "2025-01-01",
                    entry.get("data_confidence", 0.90),
                    "Structured output from Claude (claude.ai) validated against CPT 2025 / CMS PFS FY2025",
                    entry.get("rule_certainty", "mandatory"),
                    NOW, NOW,
                ),
            )
            if conn.execute("SELECT changes()").fetchone()[0]:
                cpt_inserted += 1
            else:
                # UPDATE existing with richer data
                conn.execute(
                    "UPDATE cpt_codes SET "
                    "typical_setting=?, applicable_settings=?, risk_score=?, "
                    "typical_units_max=?, requires_auth=?, specialty_typical=?, "
                    "is_add_on=?, global_period_days=?, audit_notes=?, "
                    "source_document=?, last_reviewed_at=?, data_confidence=?, "
                    "rule_certainty=?, updated_at=? "
                    "WHERE code=?",
                    (
                        entry["typical_setting"], settings_json,
                        entry["risk_score"], entry["typical_units_max"],
                        int(entry["requires_auth"]), entry["specialty_typical"],
                        int(entry["is_add_on"]), entry["global_period_days"],
                        entry.get("audit_notes"),
                        entry.get("source_document", "CPT 2025"),
                        "2025-01-01", entry.get("data_confidence", 0.90),
                        entry.get("rule_certainty", "mandatory"),
                        NOW, code,
                    ),
                )
                cpt_updated += 1

            # 4. Upsert cpt_dx_coverage rows
            for dx in entry.get("dx_coverage", []):
                conn.execute(
                    "INSERT OR IGNORE INTO cpt_dx_coverage "
                    "(cpt_code, icd_code, coverage_type, rationale, "
                    "source_authority, source_document, last_reviewed_at, "
                    "data_confidence, rule_certainty) VALUES (?,?,?,?,?,?,?,?,?)",
                    (code, dx["icd_code"], dx["coverage_type"], dx.get("rationale"),
                     "AMA" if entry["code_type"] == "cpt" else "CMS",
                     entry.get("source_document", "CPT 2025"),
                     "2025-01-01", entry.get("data_confidence", 0.85),
                     entry.get("rule_certainty", "guideline")),
                )
                if conn.execute("SELECT changes()").fetchone()[0]:
                    dx_inserted += 1

            # 5. Upsert cpt_modifier_map rows
            for m in entry.get("valid_modifiers", []):
                conn.execute(
                    "INSERT OR IGNORE INTO cpt_modifier_map "
                    "(cpt_code, modifier_code, payment_factor, ncci_override, notes, "
                    "source_authority, source_document, last_reviewed_at, "
                    "data_confidence, rule_certainty) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (code, m["modifier_code"], m.get("payment_factor"),
                     int(m.get("ncci_override", False)), m.get("notes"),
                     "AMA" if entry["code_type"] == "cpt" else "CMS",
                     entry.get("source_document", "CPT 2025"),
                     "2025-01-01", 0.90, "mandatory"),
                )
                if conn.execute("SELECT changes()").fetchone()[0]:
                    mod_map_inserted += 1

        conn.commit()
        print(
            f"  CPT/HCPCS: {cpt_inserted} inserted, {cpt_updated} updated | "
            f"{dx_inserted} dx-coverage rows | {mod_map_inserted} modifier-map rows | "
            f"{mod_inserted} new modifier codes"
        )
        return cpt_inserted + cpt_updated
    finally:
        conn.close()


if __name__ == "__main__":
    run()
