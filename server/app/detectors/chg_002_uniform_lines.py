from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim

# Two or more lines needed to establish uniformity.
_MIN_LINES = 2


class UniformLineChargesDetector(BaseDetector):
    code = "CHG-002"
    name = "Uniform Line Charges"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        lines = claim.lines or []
        if len(lines) < _MIN_LINES:
            return []

        amounts = [line.billed_amount for line in lines]
        if len(set(amounts)) > 1:
            return []

        uniform_amount = amounts[0]
        total = round(uniform_amount * len(lines), 2)

        return [DetectorResult(
            detector_code=self.code,
            finding_type="UNIFORM_LINE_CHARGES",
            description=(
                f"All {len(lines)} service lines are billed at identical amounts "
                f"(${uniform_amount:,.2f} each, ${total:,.2f} total). "
                "This pattern suggests a bulk extraction artifact or misconfigured billing system."
            ),
            overpayment_amount=0.0,
            confidence_score=0.70,
            evidence={
                "line_count": len(lines),
                "uniform_amount": round(uniform_amount, 2),
                "total_billed": total,
                "cpt_codes": [line.cpt_code for line in lines],
            },
        )]
