from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim

# Floating-point rounding can produce sub-cent differences between the header
# total and the sum of line billed_amounts. Anything within one cent is
# considered matching — below what any adjudication system would care about.
_TOLERANCE = 0.01


class ChargeTotalMismatchDetector(BaseDetector):
    code = "STR-012"
    name = "Charge Total Mismatch"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        lines = claim.lines or []
        if not lines:
            return []

        line_sum = sum(line.billed_amount for line in lines)
        header_total = claim.total_billed
        discrepancy = abs(header_total - line_sum)

        if discrepancy <= _TOLERANCE:
            return []

        return [DetectorResult(
            detector_code=self.code,
            finding_type="CHARGE_TOTAL_MISMATCH",
            description=(
                f"Header total charge (${header_total:,.2f}) does not match "
                f"sum of line billed amounts (${line_sum:,.2f}). "
                f"Discrepancy: ${discrepancy:,.2f}."
            ),
            overpayment_amount=round(discrepancy, 2),
            confidence_score=0.95,
            evidence={
                "header_total": round(header_total, 2),
                "line_sum": round(line_sum, 2),
                "discrepancy": round(discrepancy, 2),
                "line_count": len(lines),
                "lines": [
                    {
                        "line_number": line.line_number,
                        "cpt_code": line.cpt_code,
                        "billed_amount": round(line.billed_amount, 2),
                    }
                    for line in lines
                ],
            },
        )]
