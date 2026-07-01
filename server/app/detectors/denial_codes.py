"""Maps each detector rule to the official CMS Claim Adjustment Reason Code
(CARC) that best represents why the rule denies the claim.

CARC codes are the X12 835 standard adjustment reasons used on remittance advice
and denial notices. The mapping is keyed by detector_id (DET-*/STR-*/CHG-*/FWA-*/
MED-*); anything unmapped falls back to CARC 16 (the general "missing information /
billing error" code), which is the correct catch-all for structural defects.

Used by ``denial_letter_service`` to stamp the headline denial code and to label
each finding in the denial letter.
"""
from __future__ import annotations

from typing import Optional, Tuple

# detector_id -> (CARC code, official CARC description)
CARC_BY_DETECTOR: dict[str, Tuple[str, str]] = {
    # ── Structural / form-integrity (missing or malformed required data) ────
    "STR-003": ("16", "Claim/service lacks information or has submission/billing error(s)"),
    "STR-008": ("16", "Claim/service lacks information or has submission/billing error(s)"),
    "STR-009": ("16", "Claim/service lacks information or has submission/billing error(s)"),
    "STR-010": ("16", "Claim/service lacks information or has submission/billing error(s)"),
    "STR-012": ("16", "Claim/service lacks information or has submission/billing error(s)"),
    "STR-013": ("16", "Claim/service lacks information or has submission/billing error(s)"),
    "STR-014": ("31", "Patient cannot be identified as our insured"),
    # ── Charge-pattern ─────────────────────────────────────────────────────
    "CHG-002": ("16", "Claim/service lacks information or has submission/billing error(s)"),
    "CHG-003": ("16", "Claim/service lacks information or has submission/billing error(s)"),
    # ── Core payment-integrity detectors ───────────────────────────────────
    "DET-01": ("18", "Exact duplicate claim/service"),
    "DET-02": ("27", "Expenses incurred after coverage terminated"),
    "DET-04": ("45", "Charge exceeds fee schedule/maximum allowable amount"),
    "DET-06": ("97", "The benefit for this service is included in the allowance for another service already adjudicated"),
    "DET-08": ("B7", "This provider was not certified/eligible to be paid for this procedure/service on this date of service"),
    "DET-09": ("11", "The diagnosis is inconsistent with the procedure"),
    "DET-10": ("16", "Claim/service lacks information or has submission/billing error(s)"),
    "DET-13": ("16", "Claim/service lacks information or has submission/billing error(s)"),
    "DET-16": ("4", "The procedure code is inconsistent with the modifier used"),
    "DET-18": ("50", "These are non-covered services because this is not deemed a 'medical necessity' by the payer"),
    "DET-19": ("45", "Charge exceeds fee schedule/maximum allowable amount"),
    # ── Provider / FWA ─────────────────────────────────────────────────────
    "FWA-02": ("8", "The procedure code is inconsistent with the provider type/specialty"),
    "FWA-03": ("5", "The procedure code/type of bill is inconsistent with the place of service"),
    "FWA-04": ("45", "Charge exceeds fee schedule/maximum allowable amount"),
    "FWA-07": ("11", "The diagnosis is inconsistent with the procedure"),
    # ── Prior authorization ────────────────────────────────────────────────
    "MED-001": ("197", "Precertification/authorization/notification/pre-treatment absent"),
    # ── General AI audit ───────────────────────────────────────────────────
    "CG-BASIC-V1": ("16", "Claim/service lacks information or has submission/billing error(s)"),
}

DEFAULT_CARC: Tuple[str, str] = (
    "16",
    "Claim/service lacks information or has submission/billing error(s)",
)


def denial_code(detector_id: Optional[str]) -> Tuple[str, str]:
    """Return (CARC code, description) for a detector, defaulting to CARC 16."""
    if not detector_id:
        return DEFAULT_CARC
    return CARC_BY_DETECTOR.get(detector_id, DEFAULT_CARC)
