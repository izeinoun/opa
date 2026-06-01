"""FWA-03 — Place of Service (POS) mismatch.

Checks whether the POS code on each line is consistent with the kind of
procedure being billed. Common patterns SIU catches:

  - Surgical / hospital-only CPTs billed with office POS (11)
  - Office-only E/M codes billed with inpatient POS (21)
  - Procedures requiring a facility billed at home (POS 12)

Heuristic, deterministic. Runs on both pre-pay and post-pay claims.
"""
from __future__ import annotations

from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim, ClaimLine


# CMS POS code reference (the most common subset):
#   11 = Office               (in-clinic, ambulatory)
#   12 = Home
#   19 = Off-campus outpatient hospital
#   20 = Urgent care facility
#   21 = Inpatient hospital
#   22 = On-campus outpatient hospital
#   23 = Emergency room - hospital
#   24 = Ambulatory surgical center (ASC)
#   31 = Skilled nursing facility
#   81 = Independent lab

# CPT-prefix → expected-POS-set heuristics. When a billed CPT's prefix has
# a rule and the actual POS isn't in the allowed set, that's a mismatch.
# Codes not in this table are treated as POS-agnostic.
_CPT_PREFIX_RULES: dict[str, set[str]] = {
    # Hospital E/M (99221–99239): inpatient-only
    "9922": {"21", "31"},
    "9923": {"21", "31"},
    # ED E/M (99281–99285): ER-only
    "9928": {"23"},
    # Critical care (99291–99292): ER, ICU/inpatient
    "9929": {"21", "23", "22"},
    # Observation (99217–99220, 99224–99226): outpatient hospital
    "9921": {"22", "19", "21"},
    # Initial nursing facility (99304–99310): SNF
    "9930": {"31"},
    # Surgical pkg 10000s (skin, integumentary): ASC, hospital, office permitted
    "1": {"11", "22", "24", "21", "19"},
    # Cardiovascular surgery, vascular (33000–37999): ASC or hospital
    "33": {"21", "22", "24"},
    "34": {"21", "22", "24"},
    "35": {"21", "22", "24"},
    "36": {"21", "22", "24", "11", "23"},  # 36xxx includes access lines (broad)
    "37": {"21", "22", "24"},
    # Major surgical (40000–69999): hospital / ASC / office for minor
    "4": {"11", "22", "24", "21", "19"},
    "5": {"21", "22", "24", "19"},
    "6": {"11", "22", "24", "21", "19"},
    # Radiology (70000–79999): hospital, office, ASC, imaging center
    "7": {"11", "22", "24", "19", "21", "81"},
    # Path / lab (80000–89999): generally lab-only
    "8": {"81", "11", "22", "21"},
}


def _expected_pos(cpt: str) -> set[str] | None:
    if not cpt:
        return None
    # Match longest prefix that has a rule (4-char before 2-char before 1-char)
    for length in (4, 3, 2, 1):
        prefix = cpt[:length]
        if prefix in _CPT_PREFIX_RULES:
            return _CPT_PREFIX_RULES[prefix]
    return None


class POSMismatchDetector(BaseDetector):
    code = "FWA-03"
    name = "Place-of-Service Mismatch"
    fwa_rule_code = "FWA-03"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        results: List[DetectorResult] = []

        lines_res = await db_session.execute(
            select(ClaimLine).where(ClaimLine.claim_id == claim.claim_id)
        )
        lines = list(lines_res.scalars().all())
        if not lines:
            return results

        # Each line carries its own pos_code; fall back to claim.pos_code
        mismatches: list[dict] = []
        for ln in lines:
            line_pos = (ln.pos_code or claim.pos_code or "").strip()
            if not line_pos or not ln.cpt_code:
                continue
            expected = _expected_pos(ln.cpt_code)
            if expected is None or line_pos in expected:
                continue
            mismatches.append({
                "cpt":             ln.cpt_code,
                "billed_pos":      line_pos,
                "expected_pos_set": sorted(expected),
            })

        if not mismatches:
            return results

        # Confidence scales with number of mismatched lines, capped at 0.85
        # since POS errors are a recognized billing-clerk goof — not always
        # intentional fraud. The FWA flag still surfaces it for SIU review.
        confidence = min(0.85, 0.40 + 0.15 * len(mismatches))

        examples = "; ".join(
            f"CPT {m['cpt']} billed POS {m['billed_pos']} (expected one of "
            f"{','.join(m['expected_pos_set'])})"
            for m in mismatches[:5]
        )

        results.append(DetectorResult(
            detector_code=self.code,
            finding_type="pos_mismatch",
            description=(
                f"{len(mismatches)} line(s) billed with a POS code inconsistent "
                f"with the procedure: {examples}"
                + (f"; +{len(mismatches) - 5} more" if len(mismatches) > 5 else "")
            ),
            overpayment_amount=0.0,
            confidence_score=confidence,
            evidence={"mismatches": mismatches, "total_lines": len(lines)},
        ))
        return results
