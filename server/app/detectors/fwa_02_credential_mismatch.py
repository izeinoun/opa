"""FWA-02 — Credential misrepresentation.

Compares the rendering provider's registered specialty (Provider.specialty,
roughly equivalent to NPI taxonomy) against the typical specialty for each
billed CPT (CptCode.specialty_typical). A claim where, say, a Family
Medicine provider bills cardiothoracic-surgery codes is the canonical
credential-misrepresentation signal SIU watches for.

Deterministic — runs in both pre-pay and post-pay pipelines. Picks up the
FWA-02 flag automatically via BaseDetector.fwa_rule_code.
"""
from __future__ import annotations

from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim, ClaimLine
from ..models.reference import CptCode, Provider


# Specialty normalization map. Provider.specialty + CptCode.specialty_typical
# come from different vocabularies; collapse common variations to a comparable
# canonical token. Anything not in this map is compared case-insensitively
# and as-is.
_SPECIALTY_NORM = {
    "internal medicine":      "internal_medicine",
    "internal med":           "internal_medicine",
    "family medicine":        "family_medicine",
    "family practice":        "family_medicine",
    "cardiology":             "cardiology",
    "cardiovascular disease": "cardiology",
    "general surgery":        "surgery",
    "surgery":                "surgery",
    "surgical":               "surgery",
    "orthopedics":            "orthopedics",
    "orthopedic surgery":     "orthopedics",
    "oncology":               "oncology",
    "medical oncology":       "oncology",
    "hematology oncology":    "oncology",
    "radiation oncology":     "oncology",
    "emergency medicine":     "emergency_medicine",
    "anesthesiology":         "anesthesiology",
    "pediatrics":             "pediatrics",
    "psychiatry":             "psychiatry",
    "neurology":              "neurology",
    "radiology":              "radiology",
    "pathology":              "pathology",
    "dermatology":            "dermatology",
    "ophthalmology":          "ophthalmology",
    "urology":                "urology",
    "ent":                    "ent",
    "otolaryngology":         "ent",
    "obstetrics gynecology":  "ob_gyn",
    "obstetrics & gynecology": "ob_gyn",
    "ob/gyn":                 "ob_gyn",
    "obgyn":                  "ob_gyn",
}


def _norm(s: str | None) -> str:
    if not s:
        return ""
    key = s.strip().lower()
    return _SPECIALTY_NORM.get(key, key)


# E/M-style codes (99xxx) and pathology/lab CPTs are generally specialty-
# agnostic — most providers can legitimately bill them. Skip these to avoid
# noisy false positives. The "primary care can bill anything in 99xxx"
# carve-out is the most common operator complaint when this rule is too
# strict.
def _is_specialty_agnostic_cpt(cpt: str) -> bool:
    if not cpt:
        return False
    return (
        cpt.startswith("99")     # E/M, observation, hospital, ER visits
        or cpt.startswith("36")  # vascular access (broad)
        or cpt.startswith("80")  # path/lab panels
        or cpt.startswith("85")  # hematology lab
        or cpt.startswith("86")  # immunology lab
        or cpt.startswith("87")  # microbiology
    )


class CredentialMismatchDetector(BaseDetector):
    code = "FWA-02"
    name = "Credential Misrepresentation (specialty/taxonomy vs CPT)"
    fwa_rule_code = "FWA-02"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        results: List[DetectorResult] = []

        # Rendering NPI takes precedence; fall back to billing NPI.
        npi = claim.rendering_provider_npi or claim.billing_provider_npi
        if not npi:
            return results

        provider = (await db_session.execute(
            select(Provider).where(Provider.npi == npi)
        )).scalar_one_or_none()
        if provider is None or not provider.specialty:
            # Without a known specialty we can't make a credible call. Stay
            # silent rather than guess.
            return results

        provider_spec = _norm(provider.specialty)

        # Walk the lines and bucket mismatched CPTs by their typical specialty
        lines_res = await db_session.execute(
            select(ClaimLine).where(ClaimLine.claim_id == claim.claim_id)
        )
        lines = list(lines_res.scalars().all())
        if not lines:
            return results

        mismatched: list[tuple[str, str]] = []   # (cpt, expected_specialty)
        for ln in lines:
            if not ln.cpt_code or _is_specialty_agnostic_cpt(ln.cpt_code):
                continue
            cpt_row = (await db_session.execute(
                select(CptCode).where(CptCode.code == ln.cpt_code)
            )).scalar_one_or_none()
            if cpt_row is None or not cpt_row.specialty_typical:
                continue
            expected = _norm(cpt_row.specialty_typical)
            if expected and expected != provider_spec:
                mismatched.append((ln.cpt_code, cpt_row.specialty_typical))

        if not mismatched:
            return results

        # Confidence rises with the ratio of mismatched specialty-bearing
        # codes — a single rogue code on an otherwise-aligned claim is weak;
        # 3+ mismatches against the provider's specialty is strong.
        ratio = len(mismatched) / max(1, len(lines))
        confidence = min(0.95, 0.35 + 0.20 * len(mismatched))
        # Severity is implied by confidence band but FWA flag is the
        # operative bit for SIU triage.
        codes_listed = ", ".join(f"{c} (typical: {s})" for c, s in mismatched[:6])
        if len(mismatched) > 6:
            codes_listed += f", and {len(mismatched) - 6} more"

        results.append(DetectorResult(
            detector_code=self.code,
            finding_type="credential_mismatch",
            description=(
                f"Provider specialty '{provider.specialty}' does not match the "
                f"typical specialty for {len(mismatched)} billed code(s): "
                f"{codes_listed}. Possible credential misrepresentation or "
                f"NPI taxonomy/billing mismatch."
            ),
            overpayment_amount=0.0,   # advisory — no per-line dollar attribution
            confidence_score=confidence,
            evidence={
                "rendering_npi":        npi,
                "provider_specialty":   provider.specialty,
                "mismatched_codes":     [
                    {"cpt": c, "expected_specialty": s} for c, s in mismatched
                ],
                "mismatch_ratio":       round(ratio, 3),
                "total_lines":          len(lines),
            },
        ))
        return results
