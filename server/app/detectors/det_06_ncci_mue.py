from typing import List, Set, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim

NCCI_MUTUALLY_EXCLUSIVE_PAIRS: Set[Tuple[str, str]] = {
    ("99213", "99214"),
    ("27447", "27130"),
    ("43239", "43235"),
    ("70553", "70551"),
    ("93306", "93307"),
    ("99232", "99233"),
    ("36415", "36416"),
    ("20610", "20600"),
    ("97110", "97112"),
    ("11042", "11043"),
}

MUE_LIMITS = {
    "99213": 1, "99214": 1, "36415": 1, "93306": 1,
    "27447": 1, "70553": 1, "43239": 1, "97110": 4,
    "20610": 3, "11042": 1,
}


class NCCIMUEDetector(BaseDetector):
    code = "DET-06"
    name = "NCCI/MUE Violation Detector"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        results = []
        lines = claim.lines or []
        if not lines:
            return results

        cpt_set = {line.cpt_code for line in lines}

        for (cpt_a, cpt_b) in NCCI_MUTUALLY_EXCLUSIVE_PAIRS:
            if cpt_a in cpt_set and cpt_b in cpt_set:
                paid_a = sum(l.paid_amount for l in lines if l.cpt_code == cpt_a)
                paid_b = sum(l.paid_amount for l in lines if l.cpt_code == cpt_b)
                results.append(DetectorResult(
                    detector_code=self.code,
                    finding_type="NCCI_VIOLATION",
                    description=(
                        f"Mutually exclusive CPT codes billed on same claim: {cpt_a} and {cpt_b}."
                    ),
                    overpayment_amount=round(min(paid_a, paid_b), 2),
                    confidence_score=0.88,
                    evidence={
                        "cpt_code_a": cpt_a,
                        "cpt_code_b": cpt_b,
                        "paid_a": paid_a,
                        "paid_b": paid_b,
                        "claim_id": claim.claim_id,
                    },
                ))

        for line in lines:
            limit = MUE_LIMITS.get(line.cpt_code)
            if limit is not None and line.units_billed > limit:
                excess = line.units_billed - limit
                overpayment = round(line.paid_amount * (excess / line.units_billed), 2)
                results.append(DetectorResult(
                    detector_code=self.code,
                    finding_type="MUE_EXCEEDED",
                    description=(
                        f"CPT {line.cpt_code} billed with {line.units_billed} units, "
                        f"exceeding MUE limit of {limit}."
                    ),
                    overpayment_amount=overpayment,
                    confidence_score=0.88,
                    evidence={
                        "line_id": line.claim_line_id,
                        "cpt_code": line.cpt_code,
                        "billed_units": line.units_billed,
                        "mue_limit": limit,
                        "excess_units": excess,
                        "paid_amount": line.paid_amount,
                    },
                ))

        return results
