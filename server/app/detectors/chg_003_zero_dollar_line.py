from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim


class ZeroDollarLineDetector(BaseDetector):
    code = "CHG-003"
    name = "Zero Dollar Line"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        zero_lines = [
            line for line in (claim.lines or [])
            if line.billed_amount == 0.0
        ]
        if not zero_lines:
            return []

        return [DetectorResult(
            detector_code=self.code,
            finding_type="ZERO_DOLLAR_LINE",
            description=(
                f"{len(zero_lines)} service line(s) billed at $0.00. "
                "May indicate a carve-out error or misconfigured fee schedule."
            ),
            overpayment_amount=0.0,
            confidence_score=0.80,
            evidence={
                "zero_line_count": len(zero_lines),
                "lines": [
                    {
                        "line_number": line.line_number,
                        "cpt_code": line.cpt_code,
                        "billed_amount": line.billed_amount,
                    }
                    for line in zero_lines
                ],
            },
        )]
