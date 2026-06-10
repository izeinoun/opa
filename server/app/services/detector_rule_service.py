from __future__ import annotations

from typing import Dict, List, Set, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.workflow import DetectorRuleConfig



# Single source of truth for rule metadata. The DB stores enabled/score (operator-
# editable). All other fields here are re-applied on every seed_defaults() call so
# catalog metadata stays current without manual DB edits.
#
# Rules removed as duplicates of implemented DET detectors:
#   DUP-001/002/003/004  → DET-01 (duplicate billing)
#   ELG-001/002          → DET-02 (retro eligibility)
#   CHG-001              → DET-04 (fee schedule mispricing)
#   BND-001/002/004/005/009 + MUE-001/002/003 → DET-06 (NCCI/MUE)
#   PRV-006              → DET-08 (excluded provider)
#   COD-006 + MED-001 + PRV-004 → DET-09 (coding errors / credential mismatch)
#   STR-011              → FWA-03 (POS mismatch)
_RULE_DEFAULTS: List[Dict] = [
    # -------------------------------------------------------------------------
    # Implemented detectors
    # -------------------------------------------------------------------------
    {
        "rule_code": "DET-01",
        "name": "Duplicate Billing",
        "description": "Detects exact and near-duplicate claim submissions for the same member, provider, date, and procedure.",
        "layer": "Layer 8 — Duplicate Detection",
        "layer_order": 8,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": True,
        "prepay": True,
        "postpay": True,
        "rationale": "Pre-pay history lookup; post-pay recovery for missed duplicates.",
    },
    {
        "rule_code": "DET-02",
        "name": "Retro Eligibility",
        "description": "Flags services billed after the member's coverage was retroactively terminated or never effective.",
        "layer": "Layer 3 — Member / Eligibility Validation",
        "layer_order": 3,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": True,
        "prepay": True,
        "postpay": True,
        "rationale": "Eligibility known at adjudication; retroactive terminations also caught post-pay.",
    },
    {
        "rule_code": "DET-04",
        "name": "Fee Schedule Mispricing",
        "description": "Identifies paid amounts that exceed the contracted or CMS fee schedule allowed amount.",
        "layer": "Layer 11 — Charge Reasonableness",
        "layer_order": 11,
        "applies_to": "Both",
        "default_disposition": "reduce_pay",
        "has_implementation": True,
        "prepay": False,
        "postpay": True,
        "rationale": "Requires paid amount — no payment data exists pre-pay.",
    },
    {
        "rule_code": "DET-06",
        "name": "NCCI / MUE Violation",
        "description": "Detects unbundled procedure pairs and unit counts above CMS Medically Unlikely Edits limits.",
        "layer": "Layer 5 — NCCI / Bundling Edits",
        "layer_order": 5,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": True,
        "prepay": True,
        "postpay": True,
        "rationale": "NCCI table lookup is deterministic; post-pay catches missed edits.",
    },
    {
        "rule_code": "DET-08",
        "name": "Excluded Provider",
        "description": "Flags claims rendered by providers on the HHS OIG exclusion list — a hard compliance violation.",
        "layer": "Layer 2 — Provider Validation",
        "layer_order": 2,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": True,
        "prepay": True,
        "postpay": True,
        "rationale": "OIG/SAM exclusion screen. Pre-pay: block payment to an excluded provider. Post-pay: recover payments already made to one (matched against the OIG LEIE by rendering NPI).",
    },
    {
        "rule_code": "DET-09",
        "name": "Coding Errors",
        "description": "Detects upcoding, DX/CPT mismatches, and unbundling of comprehensive codes into component codes.",
        "layer": "Layer 4 — Code Validity",
        "layer_order": 4,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": True,
        "prepay": True,
        "postpay": True,
        "rationale": "Dx/CPT mismatch is pre-pay deterministic; unbundling patterns also surfaced post-pay.",
    },
    # FWA detectors — deterministic. FWA-04 + FWA-07 are LLM-assisted and
    # live outside the orchestrator, so they aren't toggleable via this
    # config table (they're gated by the ANTHROPIC_API_KEY presence instead).
    {
        "rule_code": "FWA-02",
        "name": "Credential Misrepresentation",
        "description": "Compares rendering provider's specialty against the typical specialty for each billed CPT. Flags claims where the provider's NPI taxonomy doesn't fit the billed procedures.",
        "layer": "Layer 2 — Provider Validation",
        "layer_order": 2,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": True,
        "prepay": True,
        "postpay": True,
        "rationale": "Hard specialty mismatches are pre-pay; pattern analysis across volume is post-pay.",
    },
    {
        "rule_code": "FWA-03",
        "name": "Place-of-Service Mismatch",
        "description": "Flags claim lines where the billed POS code is inconsistent with the procedure type (e.g. inpatient-only CPT billed with an office POS).",
        "layer": "Layer 7 — Medical Necessity",
        "layer_order": 7,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": True,
        "prepay": True,
        "postpay": True,
        "rationale": "POS code check is deterministic on any claim form.",
    },
    {
        "rule_code": "DET-13",
        "name": "Code Validity",
        "description": "Validates CPT and ICD-10 codes on the claim against loaded CMS reference tables. Flags codes absent from the reference data.",
        "layer": "Layer 4 — Code Validity",
        "layer_order": 4,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": True,
        "prepay": True,
        "postpay": True,
        "rationale": "Static table lookup; valid pre-pay (stop bad codes) and post-pay (recoup for services billed under invalid codes).",
    },
    {
        "rule_code": "DET-16",
        "name": "Modifier Integrity",
        "description": (
            "Validates modifier usage on each claim line: detects unrecognized modifiers, "
            "mutually exclusive modifier pairs on the same line (e.g. 26 + TC), modifiers "
            "applied to incompatible CPT types (e.g. modifier 25 on a surgical code), and "
            "modifier 25 present without any same-day procedure code on the claim."
        ),
        "layer": "Layer 4 — Code Validity",
        "layer_order": 4,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": True,
        "prepay": True,
        "postpay": True,
        "rationale": "Modifier table lookup and claim-level logic; valid both pre-pay and post-pay.",
    },
    {
        "rule_code": "DET-10",
        "name": "Bill Type / Revenue Code Validity",
        "description": (
            "Validates bill type and revenue codes on institutional (UB-04) claims against "
            "reference tables. Fires for missing or unrecognized bill type and for any line "
            "with a missing or unrecognized revenue code."
        ),
        "layer": "Layer 4 — Code Validity",
        "layer_order": 4,
        "applies_to": "Institutional",
        "default_disposition": "suspend_review",
        "has_implementation": True,
        "prepay": True,
        "postpay": True,
        "rationale": "UB-04 bill type and revenue codes are required for facility claims; invalid codes block adjudication.",
    },

    # -------------------------------------------------------------------------
    # Layer 1 — Structural / Form Validity
    # -------------------------------------------------------------------------
    {
        "rule_code": "STR-001",
        "name": "Missing Bill Type",
        "description": "UB-04 FL4 Bill Type code is required on all institutional claims.",
        "layer": "Layer 1 — Structural / Form Validity",
        "layer_order": 1,
        "applies_to": "Institutional",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Hard stop; claim can't adjudicate.",
    },
    {
        "rule_code": "STR-002",
        "name": "Invalid Bill Type",
        "description": "Bill Type code must be a recognized CMS Bill Type value.",
        "layer": "Layer 1 — Structural / Form Validity",
        "layer_order": 1,
        "applies_to": "Institutional",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Hard stop.",
    },
    {
        "rule_code": "STR-003",
        "name": "Revenue Code on Professional Claim",
        "description": (
            "Revenue code is present on a CMS-1500 professional claim line. "
            "Revenue codes are UB-04 institutional fields (FL 42) and must not appear "
            "on professional claims — indicates a form-type mismatch or data entry error."
        ),
        "layer": "Layer 1 — Structural / Form Validity",
        "layer_order": 1,
        "applies_to": "Professional",
        "default_disposition": "suspend_review",
        "has_implementation": True,
        "prepay": True,
        "postpay": True,
        "rationale": "Structural mismatch; revenue codes are institutional-only fields.",
    },
    {
        "rule_code": "STR-004",
        "name": "Revenue Code / CPT Mismatch",
        "description": "Revenue code on a line must be compatible with the billed CPT/HCPCS code.",
        "layer": "Layer 1 — Structural / Form Validity",
        "layer_order": 1,
        "applies_to": "Institutional",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Deterministic table lookup.",
    },
    {
        "rule_code": "STR-005",
        "name": "Missing Attending NPI",
        "description": "UB-04 Box 56/76 attending physician NPI is required on institutional claims.",
        "layer": "Layer 1 — Structural / Form Validity",
        "layer_order": 1,
        "applies_to": "Institutional",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Hard stop.",
    },
    {
        "rule_code": "STR-006",
        "name": "Missing Rendering NPI",
        "description": "CMS-1500 Box 24J rendering provider NPI is required on professional claims.",
        "layer": "Layer 1 — Structural / Form Validity",
        "layer_order": 1,
        "applies_to": "Professional",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Hard stop.",
    },
    {
        "rule_code": "STR-007",
        "name": "NPI Format Invalid",
        "description": "NPI must be a 10-digit Luhn-valid number per HIPAA standard.",
        "layer": "Layer 1 — Structural / Form Validity",
        "layer_order": 1,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Luhn check; instant.",
    },
    {
        "rule_code": "STR-008",
        "name": "Missing Date of Service",
        "description": "At least one date of service is required on every claim.",
        "layer": "Layer 1 — Structural / Form Validity",
        "layer_order": 1,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": True,
        "prepay": True,
        "postpay": False,
        "rationale": "Hard stop.",
    },
    {
        "rule_code": "STR-009",
        "name": "DOS in Future",
        "description": "Service date cannot exceed the claim receipt date.",
        "layer": "Layer 1 — Structural / Form Validity",
        "layer_order": 1,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": True,
        "prepay": True,
        "postpay": False,
        "rationale": "Date comparison.",
    },
    {
        "rule_code": "STR-010",
        "name": "Missing Primary Diagnosis",
        "description": "At least one ICD-10 diagnosis code is required on every claim.",
        "layer": "Layer 1 — Structural / Form Validity",
        "layer_order": 1,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": True,
        "prepay": True,
        "postpay": False,
        "rationale": "Hard stop.",
    },
    # STR-011 (Missing Place of Service) removed — covered by FWA-03.
    {
        "rule_code": "STR-012",
        "name": "Claim Total Mismatch",
        "description": "Sum of individual line charges must equal the header total charge.",
        "layer": "Layer 1 — Structural / Form Validity",
        "layer_order": 1,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": True,
        "prepay": True,
        "postpay": False,
        "rationale": "Math check.",
    },
    {
        "rule_code": "STR-013",
        "name": "Missing Patient DOB",
        "description": "Patient date of birth is required for age-based coverage and medical necessity edits.",
        "layer": "Layer 1 — Structural / Form Validity",
        "layer_order": 1,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": True,
        "prepay": True,
        "postpay": False,
        "rationale": "Required for downstream edits.",
    },
    {
        "rule_code": "STR-014",
        "name": "Missing Member ID",
        "description": "Payer member identifier is required to link the claim to an eligibility record.",
        "layer": "Layer 1 — Structural / Form Validity",
        "layer_order": 1,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": True,
        "prepay": True,
        "postpay": False,
        "rationale": "Hard stop.",
    },

    # -------------------------------------------------------------------------
    # Layer 2 — Provider Validation
    # PRV-004 removed — covered by FWA-02 (credential misrepresentation).
    # PRV-006 removed — covered by DET-08 (excluded provider).
    # -------------------------------------------------------------------------
    {
        "rule_code": "PRV-001",
        "name": "NPI Not Found in NPPES",
        "description": "NPI must be active and present in the NPPES registry.",
        "layer": "Layer 2 — Provider Validation",
        "layer_order": 2,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Real-time NPPES lookup.",
    },
    {
        "rule_code": "PRV-002",
        "name": "NPI Deactivated",
        "description": "Provider NPI has been deactivated in NPPES and is no longer valid for billing.",
        "layer": "Layer 2 — Provider Validation",
        "layer_order": 2,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Real-time NPPES lookup.",
    },
    {
        "rule_code": "PRV-003",
        "name": "Provider Not in Network",
        "description": "Rendering or billing NPI is not under active contract with this payer.",
        "layer": "Layer 2 — Provider Validation",
        "layer_order": 2,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Roster lookup; known at claim time.",
    },
    {
        "rule_code": "PRV-005",
        "name": "Rendering NPI / Billing NPI Conflict",
        "description": "Group NPI billed as rendering or individual NPI billed as group — creates pay-to routing errors.",
        "layer": "Layer 2 — Provider Validation",
        "layer_order": 2,
        "applies_to": "Professional",
        "default_disposition": "suspend_review",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Structural check.",
    },
    {
        "rule_code": "PRV-007",
        "name": "Facility Not Credentialed",
        "description": "Institutional provider has not been approved by this payer for the submitted bill type.",
        "layer": "Layer 2 — Provider Validation",
        "layer_order": 2,
        "applies_to": "Institutional",
        "default_disposition": "suspend_review",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Credentialing file lookup.",
    },
    {
        "rule_code": "PRV-008",
        "name": "Out-of-State License",
        "description": "Provider is licensed in a different state than the state where service was rendered.",
        "layer": "Layer 2 — Provider Validation",
        "layer_order": 2,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": False,
        "prepay": True,
        "postpay": True,
        "rationale": "Pre-pay if licensure data available; otherwise post-pay audit.",
    },

    # -------------------------------------------------------------------------
    # Layer 3 — Member / Eligibility Validation
    # ELG-001 removed — covered by DET-02 (retro eligibility).
    # ELG-002 removed — covered by DET-02 (retro eligibility).
    # -------------------------------------------------------------------------
    {
        "rule_code": "ELG-003",
        "name": "Benefit Not Covered",
        "description": "The service category is excluded from the member's plan benefits.",
        "layer": "Layer 3 — Member / Eligibility Validation",
        "layer_order": 3,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Benefits table lookup.",
    },
    {
        "rule_code": "ELG-004",
        "name": "Medicare as Secondary Payer",
        "description": "COB order is incorrect — Medicare should be secondary per MSP rules.",
        "layer": "Layer 3 — Member / Eligibility Validation",
        "layer_order": 3,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": False,
        "prepay": True,
        "postpay": True,
        "rationale": "Pre-pay when MSP file available; post-pay audit for missed cases.",
    },
    {
        "rule_code": "ELG-005",
        "name": "Wrong Payer Billed",
        "description": "COB data indicates another payer is primary; this payer should not be receiving the claim first.",
        "layer": "Layer 3 — Member / Eligibility Validation",
        "layer_order": 3,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "COB order in eligibility file.",
    },
    {
        "rule_code": "ELG-006",
        "name": "Age / Sex Benefit Mismatch",
        "description": "Service is not covered for the member's age or sex per plan benefits.",
        "layer": "Layer 3 — Member / Eligibility Validation",
        "layer_order": 3,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "DOB + sex on eligibility file.",
    },

    # -------------------------------------------------------------------------
    # Layer 4 — Code Validity
    # COD-006 removed — covered by DET-09 (coding errors).
    # -------------------------------------------------------------------------
    {
        "rule_code": "COD-001",
        "name": "Invalid CPT Code",
        "description": "CPT code is not present in the current AMA code set.",
        "layer": "Layer 4 — Code Validity",
        "layer_order": 4,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Static table lookup.",
    },
    {
        "rule_code": "COD-002",
        "name": "CPT Inactive for DOS",
        "description": "CPT code was deleted or not yet effective on the date of service.",
        "layer": "Layer 4 — Code Validity",
        "layer_order": 4,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Effective date table lookup.",
    },
    {
        "rule_code": "COD-003",
        "name": "Invalid ICD-10 Code",
        "description": "Diagnosis code is not present in the current CMS ICD-10-CM table.",
        "layer": "Layer 4 — Code Validity",
        "layer_order": 4,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Static table lookup.",
    },
    {
        "rule_code": "COD-004",
        "name": "ICD-10 Inactive for DOS",
        "description": "Diagnosis code was deleted or not yet effective on the date of service.",
        "layer": "Layer 4 — Code Validity",
        "layer_order": 4,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Effective date table lookup.",
    },
    {
        "rule_code": "COD-005",
        "name": "Invalid HCPCS Code",
        "description": "Level II HCPCS code is not present in the current CMS HCPCS table.",
        "layer": "Layer 4 — Code Validity",
        "layer_order": 4,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Static table lookup.",
    },
    {
        "rule_code": "COD-007",
        "name": "Invalid Modifier",
        "description": "Modifier is not recognized or is not applicable to the billed CPT code.",
        "layer": "Layer 4 — Code Validity",
        "layer_order": 4,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Modifier table lookup.",
    },
    {
        "rule_code": "COD-008",
        "name": "Invalid Revenue Code",
        "description": "Revenue code is not present in the current UB-04 valid revenue code list.",
        "layer": "Layer 4 — Code Validity",
        "layer_order": 4,
        "applies_to": "Institutional",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "UB-04 table lookup.",
    },
    {
        "rule_code": "COD-009",
        "name": "Diagnosis is Manifestation Code",
        "description": "A manifestation code is billed without its required underlying etiology code.",
        "layer": "Layer 4 — Code Validity",
        "layer_order": 4,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "ICD-10 tabular flag.",
    },
    {
        "rule_code": "COD-010",
        "name": "Diagnosis Sequencing Error",
        "description": "Manifestation code is sequenced before the underlying condition code.",
        "layer": "Layer 4 — Code Validity",
        "layer_order": 4,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "ICD-10 sequencing rules.",
    },

    # -------------------------------------------------------------------------
    # Layer 5 — NCCI / Bundling Edits
    # BND-001/002/004/005/009 removed — covered by DET-06 (NCCI/MUE).
    # -------------------------------------------------------------------------
    {
        "rule_code": "BND-003",
        "name": "Modifier 59 Overuse",
        "description": "Modifier 59 is applied without documentation supporting a distinct procedure or service.",
        "layer": "Layer 5 — NCCI / Bundling Edits",
        "layer_order": 5,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": False,
        "prepay": True,
        "postpay": True,
        "rationale": "Single claim flag pre-pay; pattern analysis is post-pay.",
    },
    {
        "rule_code": "BND-006",
        "name": "Assistant Surgeon Not Payable",
        "description": "CPT code is flagged in the CMS fee schedule as not allowing assistant surgeon billing.",
        "layer": "Layer 5 — NCCI / Bundling Edits",
        "layer_order": 5,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "CPT indicator flag.",
    },
    {
        "rule_code": "BND-007",
        "name": "Bilateral Procedure — Wrong Units",
        "description": "Bilateral modifier (50) should be used instead of billing 2 units for a bilateral procedure.",
        "layer": "Layer 5 — NCCI / Bundling Edits",
        "layer_order": 5,
        "applies_to": "Both",
        "default_disposition": "reduce_pay",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Deterministic.",
    },
    {
        "rule_code": "BND-008",
        "name": "Add-On Code Without Primary",
        "description": "An add-on CPT code is billed without its required parent procedure code.",
        "layer": "Layer 5 — NCCI / Bundling Edits",
        "layer_order": 5,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "CPT add-on table.",
    },

    # -------------------------------------------------------------------------
    # Layer 6 — Medically Unlikely Edits
    # MUE-001/002/003 removed — covered by DET-06 (NCCI/MUE).
    # -------------------------------------------------------------------------
    {
        "rule_code": "MUE-004",
        "name": "Anesthesia Units — Time Mismatch",
        "description": "Anesthesia base units plus time units do not reconcile with the reported procedure time.",
        "layer": "Layer 6 — Medically Unlikely Edits",
        "layer_order": 6,
        "applies_to": "Both",
        "default_disposition": "reduce_pay",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Formula-based.",
    },

    # -------------------------------------------------------------------------
    # Layer 7 — Medical Necessity
    # MED-001 removed — covered by DET-09 (coding errors / Dx-CPT linkage).
    # -------------------------------------------------------------------------
    {
        "rule_code": "DET-18",
        "name": "Medical Necessity",
        "description": (
            "Flags CPT codes billed without any covered diagnosis. Queries the "
            "cpt_dx_coverage table (LCD/NCD-backed required and supporting diagnosis "
            "rules) and fires when a CPT has defined coverage criteria but none of the "
            "claim's ICD codes satisfy any of them."
        ),
        "layer": "Layer 7 — Medical Necessity",
        "layer_order": 7,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": True,
        "prepay": True,
        "postpay": True,
        "rationale": "LCD/NCD table lookup; no documentation required — codes-only check.",
    },
    {
        "rule_code": "MED-002",
        "name": "LCD Indication Not Met",
        "description": "A diagnosis is present but it is not on the covered indication list for this CPT under the applicable LCD.",
        "layer": "Layer 7 — Medical Necessity",
        "layer_order": 7,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "LCD covered diagnosis list lookup.",
    },
    {
        "rule_code": "MED-003",
        "name": "NCD Exclusion",
        "description": "Service is excluded under a National Coverage Determination.",
        "layer": "Layer 7 — Medical Necessity",
        "layer_order": 7,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "NCD table lookup.",
    },
    {
        "rule_code": "MED-004",
        "name": "Frequency Limit Exceeded",
        "description": "Same service has been billed more often than the plan's frequency policy allows.",
        "layer": "Layer 7 — Medical Necessity",
        "layer_order": 7,
        "applies_to": "Both",
        "default_disposition": "reduce_pay",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Requires claims history query — feasible pre-pay.",
    },
    {
        "rule_code": "MED-005",
        "name": "Age Not Covered",
        "description": "CPT code is not covered for the member's age per the applicable LCD.",
        "layer": "Layer 7 — Medical Necessity",
        "layer_order": 7,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "DOB + LCD age criteria.",
    },
    {
        "rule_code": "MED-006",
        "name": "Sex Not Covered",
        "description": "CPT code is not covered for the member's sex.",
        "layer": "Layer 7 — Medical Necessity",
        "layer_order": 7,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Sex + LCD criteria.",
    },
    {
        "rule_code": "MED-007",
        "name": "Screening vs Diagnostic Conflict",
        "description": "Screening CPT code is billed alongside a symptomatic diagnosis, which converts it to a diagnostic service.",
        "layer": "Layer 7 — Medical Necessity",
        "layer_order": 7,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Code pairing rule.",
    },
    {
        "rule_code": "MED-008",
        "name": "Preventive Service Billed as Diagnostic",
        "description": "Preventive CPT code is paired with an acute or problem-based diagnosis.",
        "layer": "Layer 7 — Medical Necessity",
        "layer_order": 7,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Code pairing rule.",
    },

    # -------------------------------------------------------------------------
    # Layer 8 — Duplicate Detection
    # DUP-001/002/003/004 removed — covered by DET-01 (duplicate billing).
    # -------------------------------------------------------------------------
    {
        "rule_code": "DUP-005",
        "name": "Cross-Payer Duplicate",
        "description": "Same service has already been paid by another payer per COB cross-check.",
        "layer": "Layer 8 — Duplicate Detection",
        "layer_order": 8,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": False,
        "prepay": True,
        "postpay": True,
        "rationale": "Requires external payer data; usually post-pay.",
    },

    # -------------------------------------------------------------------------
    # Layer 9 — Global Period / Surgical Package
    # -------------------------------------------------------------------------
    {
        "rule_code": "GLB-001",
        "name": "Service in Global Period",
        "description": "CPT is billed during the 10- or 90-day global period of another previously paid procedure.",
        "layer": "Layer 9 — Global Period / Surgical Package",
        "layer_order": 9,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "CMS global period table + claims history.",
    },
    {
        "rule_code": "GLB-002",
        "name": "E&M in Global Period — No Modifier",
        "description": "E&M service billed during a global period without the required modifier 24.",
        "layer": "Layer 9 — Global Period / Surgical Package",
        "layer_order": 9,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Same logic as GLB-001.",
    },
    {
        "rule_code": "GLB-003",
        "name": "Pre-Op Billed Separately",
        "description": "Pre-operative visit billed within the surgical package window — it is included in the surgical fee.",
        "layer": "Layer 9 — Global Period / Surgical Package",
        "layer_order": 9,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Date window calculation.",
    },
    {
        "rule_code": "GLB-004",
        "name": "Post-Op Billed Separately",
        "description": "Post-operative care billed separately within the global period — it is included in the surgical fee.",
        "layer": "Layer 9 — Global Period / Surgical Package",
        "layer_order": 9,
        "applies_to": "Both",
        "default_disposition": "auto_deny",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Date window calculation.",
    },

    # -------------------------------------------------------------------------
    # Layer 10 — Coordination of Benefits
    # -------------------------------------------------------------------------
    {
        "rule_code": "COB-001",
        "name": "Primary EOB Missing",
        "description": "Secondary claim submitted without the required primary payer EOB.",
        "layer": "Layer 10 — Coordination of Benefits",
        "layer_order": 10,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": False,
        "prepay": True,
        "postpay": False,
        "rationale": "Secondary claim structural check.",
    },
    {
        "rule_code": "COB-002",
        "name": "Other Insurance Not Reported",
        "description": "Eligibility file shows other coverage but no COB data is present on the claim.",
        "layer": "Layer 10 — Coordination of Benefits",
        "layer_order": 10,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": False,
        "prepay": True,
        "postpay": True,
        "rationale": "Pre-pay if COB file current; often caught post-pay.",
    },
    {
        "rule_code": "COB-003",
        "name": "Overpayment Risk — COB Math",
        "description": "Combined primary and secondary payments would exceed the allowed amount.",
        "layer": "Layer 10 — Coordination of Benefits",
        "layer_order": 10,
        "applies_to": "Both",
        "default_disposition": "reduce_pay",
        "has_implementation": False,
        "prepay": True,
        "postpay": True,
        "rationale": "Math is pre-pay; recovery is post-pay.",
    },
    {
        "rule_code": "COB-004",
        "name": "Workers Comp — Should Be Primary",
        "description": "Injury-related diagnosis is present but workers compensation payer was not billed first.",
        "layer": "Layer 10 — Coordination of Benefits",
        "layer_order": 10,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": False,
        "prepay": True,
        "postpay": True,
        "rationale": "Injury code flag pre-pay; confirmation post-pay.",
    },
    {
        "rule_code": "COB-005",
        "name": "Auto Liability — Should Be Primary",
        "description": "MVA-related diagnosis is present but no-fault auto liability payer was not listed as primary.",
        "layer": "Layer 10 — Coordination of Benefits",
        "layer_order": 10,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": False,
        "prepay": True,
        "postpay": True,
        "rationale": "Same as COB-004.",
    },

    # -------------------------------------------------------------------------
    # Layer 11 — Charge Reasonableness
    # CHG-001 removed — covered by DET-04 (fee schedule mispricing).
    # -------------------------------------------------------------------------
    {
        "rule_code": "CHG-002",
        "name": "Uniform Line Charges",
        "description": "All lines are billed at identical amounts, suggesting a bulk extraction or billing system artifact.",
        "layer": "Layer 11 — Charge Reasonableness",
        "layer_order": 11,
        "applies_to": "Both",
        "default_disposition": "suspend_review",
        "has_implementation": True,
        "prepay": True,
        "postpay": False,
        "rationale": "Extraction artifact; flag before payment.",
    },
    {
        "rule_code": "CHG-003",
        "name": "Zero Dollar Line",
        "description": "A line item is billed at $0, which may indicate a carve-out error or misconfigured fee schedule.",
        "layer": "Layer 11 — Charge Reasonableness",
        "layer_order": 11,
        "applies_to": "Both",
        "default_disposition": "pay_log_only",
        "has_implementation": True,
        "prepay": True,
        "postpay": False,
        "rationale": "Simple check.",
    },
    {
        "rule_code": "CHG-004",
        "name": "Charge-to-Allowed Ratio Outlier",
        "description": "Provider's charge-to-allowed ratio is a statistical outlier relative to peer providers for the same CPT.",
        "layer": "Layer 11 — Charge Reasonableness",
        "layer_order": 11,
        "applies_to": "Both",
        "default_disposition": "pay_log_only",
        "has_implementation": False,
        "prepay": False,
        "postpay": True,
        "rationale": "Requires peer comparison across claim volume.",
    },

    # -------------------------------------------------------------------------
    # Layer 12 — Provider Behavior / Risk Scoring
    # -------------------------------------------------------------------------
    {
        "rule_code": "RSK-001",
        "name": "High-Volume Same-Day Services",
        "description": "Provider is billing an unusually high volume of CPT units per day compared to peers.",
        "layer": "Layer 12 — Provider Behavior / Risk Scoring",
        "layer_order": 12,
        "applies_to": "Both",
        "default_disposition": "pay_log_only",
        "has_implementation": False,
        "prepay": True,
        "postpay": True,
        "rationale": "Single claim flag; pattern confirmation post-pay.",
    },
    {
        "rule_code": "RSK-002",
        "name": "Upcoding Pattern",
        "description": "Provider consistently bills the highest-level E&M codes at a rate significantly above peer average.",
        "layer": "Layer 12 — Provider Behavior / Risk Scoring",
        "layer_order": 12,
        "applies_to": "Both",
        "default_disposition": "request_adr",
        "has_implementation": False,
        "prepay": False,
        "postpay": True,
        "rationale": "Requires historical volume across claims.",
    },
    {
        "rule_code": "RSK-003",
        "name": "Unbundling Pattern",
        "description": "Provider repeatedly bills component codes instead of the appropriate comprehensive panel or package code.",
        "layer": "Layer 12 — Provider Behavior / Risk Scoring",
        "layer_order": 12,
        "applies_to": "Both",
        "default_disposition": "request_adr",
        "has_implementation": False,
        "prepay": False,
        "postpay": True,
        "rationale": "Requires historical volume.",
    },
    {
        "rule_code": "RSK-004",
        "name": "High MUE Proximity",
        "description": "Provider regularly bills at or very near the MUE ceiling for multiple codes.",
        "layer": "Layer 12 — Provider Behavior / Risk Scoring",
        "layer_order": 12,
        "applies_to": "Both",
        "default_disposition": "pay_log_only",
        "has_implementation": False,
        "prepay": False,
        "postpay": True,
        "rationale": "Requires historical volume.",
    },
    {
        "rule_code": "RSK-005",
        "name": "New Provider — Outlier Billing",
        "description": "Recently credentialed provider is billing an atypical service mix relative to their specialty.",
        "layer": "Layer 12 — Provider Behavior / Risk Scoring",
        "layer_order": 12,
        "applies_to": "Both",
        "default_disposition": "pay_log_only",
        "has_implementation": False,
        "prepay": True,
        "postpay": True,
        "rationale": "Flag pre-pay; investigate post-pay.",
    },
    {
        "rule_code": "RSK-006",
        "name": "Modifier Abuse Pattern",
        "description": "Modifier 59 or 25 is applied on an unusually high percentage of this provider's claims.",
        "layer": "Layer 12 — Provider Behavior / Risk Scoring",
        "layer_order": 12,
        "applies_to": "Both",
        "default_disposition": "request_adr",
        "has_implementation": False,
        "prepay": False,
        "postpay": True,
        "rationale": "Requires historical modifier usage across claims.",
    },
]

# Catalog fields that are seeded from _RULE_DEFAULTS — not operator-editable.
_CATALOG_FIELDS = (
    "name", "description", "layer", "layer_order", "applies_to",
    "default_disposition", "has_implementation", "prepay", "postpay", "rationale",
)


async def seed_defaults(db: AsyncSession) -> None:
    """Upsert catalog metadata for all rules.

    Operator-editable fields (enabled, score) are only written on INSERT;
    catalog metadata fields are re-applied on every call so the DB stays in
    sync with _RULE_DEFAULTS without manual SQL.
    """
    result = await db.execute(select(DetectorRuleConfig.rule_code))
    existing = {r for (r,) in result.all()}

    for spec in _RULE_DEFAULTS:
        code = spec["rule_code"]
        catalog_vals = {f: spec[f] for f in _CATALOG_FIELDS}
        if code not in existing:
            db.add(DetectorRuleConfig(
                rule_code=code,
                enabled_prepay=spec["has_implementation"] and spec["prepay"],
                enabled_postpay=spec["has_implementation"] and spec["postpay"],
                score=1.0,
                **catalog_vals,
            ))
        else:
            await db.execute(
                update(DetectorRuleConfig)
                .where(DetectorRuleConfig.rule_code == code)
                .values(**catalog_vals)
            )
            # First-activation: if has_implementation just became True and the
            # rule has never been operator-touched (both flags still False from
            # the original unimplemented seed), promote it to enabled.
            if spec["has_implementation"]:
                await db.execute(
                    update(DetectorRuleConfig)
                    .where(
                        DetectorRuleConfig.rule_code == code,
                        DetectorRuleConfig.enabled_prepay == False,
                        DetectorRuleConfig.enabled_postpay == False,
                    )
                    .values(
                        enabled_prepay=spec["prepay"],
                        enabled_postpay=spec["postpay"],
                    )
                )

    await db.flush()


async def get_all(db: AsyncSession) -> List[DetectorRuleConfig]:
    await seed_defaults(db)
    result = await db.execute(
        select(DetectorRuleConfig).order_by(
            DetectorRuleConfig.layer_order, DetectorRuleConfig.rule_code
        )
    )
    return list(result.scalars().all())


async def get_runtime_config(
    db: AsyncSession, pipeline_mode: str = "post_pay"
) -> tuple[Set[str], Dict[str, float]]:
    """Returns (enabled_codes, score_multipliers_by_code) for the given pipeline.

    A rule enters the enabled set only when BOTH conditions hold:
      - structural eligibility: the catalog flag (prepay/postpay) is True
      - operator toggle: enabled_prepay/enabled_postpay is True
    This prevents rules from running in a pipeline whose data model they
    can't satisfy (e.g. DET-04 needs total_paid which doesn't exist pre-pay).
    """
    rules = await get_all(db)
    if pipeline_mode == "pre_pay":
        enabled = {r.rule_code for r in rules if r.prepay and r.enabled_prepay}
    else:
        enabled = {r.rule_code for r in rules if r.postpay and r.enabled_postpay}
    multipliers = {r.rule_code: r.score for r in rules}
    return enabled, multipliers


async def get_by_code(db: AsyncSession, rule_code: str) -> Optional[DetectorRuleConfig]:
    result = await db.execute(
        select(DetectorRuleConfig).where(DetectorRuleConfig.rule_code == rule_code)
    )
    return result.scalar_one_or_none()
