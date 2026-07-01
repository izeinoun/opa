"""Generic, per-rule descriptions — "what this rule checks", independent of any
one claim.

These mirror PayGuard's finding-card layout, where each fired rule shows a short
static description of the rule above the claim-specific explanation. The text
here is deterministic and identical across claims (cheap, consistent); the
claim-specific plain-English explanation is generated per finding by
``finding_explanation_service`` and stored on ``findings.issue_summary``.

Keyed by detector code (DET-*/STR-*/CHG-*/MED-*/FWA-*/CG-BASIC-V1). ``describe``
returns ``None`` for unknown codes so callers can omit the line rather than show
a placeholder.
"""
from __future__ import annotations

from typing import Optional

RULE_DESCRIPTIONS: dict[str, str] = {
    # ── Structural / form-integrity rules (STR-*) ──────────────────────────
    "STR-003": "Flags revenue codes billed on a professional (CMS-1500) claim, "
               "where revenue codes do not belong — they are an institutional "
               "(UB-04) construct.",
    "STR-008": "Flags a claim submitted without a date of service, which is "
               "required to adjudicate timeliness, eligibility, and coverage.",
    "STR-009": "Flags a date of service that falls in the future, which cannot "
               "be valid for a submitted claim.",
    "STR-010": "Flags a claim submitted without a primary diagnosis, which is "
               "required for medical-necessity and coverage determination.",
    "STR-012": "Flags a claim whose header charge total does not equal the sum "
               "of its service-line charges.",
    "STR-013": "Flags a claim form submitted without a patient date of birth, "
               "which is required on the claim for age-based coverage and "
               "medical-necessity edits.",
    "STR-014": "Flags a claim submitted without a member/subscriber ID, which "
               "is required to match the patient to an eligible policy.",
    # ── Charge-pattern rules (CHG-*) ───────────────────────────────────────
    "CHG-002": "Flags claims whose service lines carry suspiciously uniform "
               "charges, a pattern associated with templated or fabricated "
               "billing.",
    "CHG-003": "Flags service lines billed at zero dollars, which may indicate "
               "an unbundling or data-entry error.",
    # ── Core payment-integrity detectors (DET-*) ───────────────────────────
    "DET-01": "Flags a claim that duplicates the same member, procedure, and "
              "date of service as a prior claim.",
    "DET-02": "Flags a member who was not enrolled/eligible on the date of "
              "service.",
    "DET-04": "Flags paid or billed amounts that exceed the contracted or "
              "allowable rate from the provider's fee schedule for the "
              "applicable line of business.",
    "DET-06": "Flags NCCI mutually-exclusive procedure pairs and units that "
              "exceed the CMS Medically Unlikely Edit (MUE) limit.",
    "DET-08": "Flags a rendering provider that appears on the OIG/SAM federal "
              "exclusion list and is ineligible to bill.",
    "DET-09": "Flags coding and documentation errors — invalid ICD→CPT "
              "combinations, unbundling, and form-type coding violations.",
    "DET-10": "Flags bill-type and revenue-code combinations that are invalid "
              "for the claim's care setting.",
    "DET-13": "Flags CPT, ICD-10, or DRG codes that are not found in the loaded "
              "CMS reference tables or are not valid for the date of service.",
    "DET-16": "Flags missing, invalid, or conflicting procedure modifiers.",
    "DET-18": "Flags procedures billed without a diagnosis that satisfies the "
              "applicable LCD/NCD medical-necessity coverage rules.",
    "DET-19": "Flags evaluation-and-management levels billed higher than the "
              "documentation or visit complexity supports (upcoding).",
    # ── Prior authorization ────────────────────────────────────────────────
    "MED-001": "Flags procedures that require prior authorization where no "
               "approved authorization is on file.",
    # ── FWA signals ────────────────────────────────────────────────────────
    "FWA-04": "Flags upcoding patterns where billed services are systematically "
              "more intensive than clinically supported.",
    "FWA-07": "Flags diagnosis inflation — diagnoses added to justify a higher "
              "level of service or reimbursement.",
    # ── General AI audit ───────────────────────────────────────────────────
    "CG-BASIC-V1": "AI-assisted audit of the full claim against coding, "
                   "coverage, and documentation guidelines.",
}


def describe(detector_code: Optional[str]) -> Optional[str]:
    """Return the generic rule description for a detector code, or None."""
    if not detector_code:
        return None
    return RULE_DESCRIPTIONS.get(detector_code)
