from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim
from ..dao.fee_schedule_dao import FeeScheduleDAO

TOLERANCE = 0.05


class FeeScheduleDetector(BaseDetector):
    code = "DET-04"
    name = "Fee Schedule Variance Detector"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        results = []
        fee_dao = FeeScheduleDAO(db_session)

        total_overpayment = 0.0
        violating_lines = []

        for line in (claim.lines or []):
            allowed = await fee_dao.get_allowed_amount(
                cpt_code=line.cpt_code,
                lob=claim.lob,
                service_date=claim.service_from_date,
            )
            if allowed is None:
                continue

            threshold = allowed * (1.0 + TOLERANCE)
            if line.paid_amount > threshold:
                overpayment = line.paid_amount - allowed
                total_overpayment += overpayment
                violating_lines.append({
                    "line_id": line.claim_line_id,
                    "line_number": line.line_number,
                    "cpt_code": line.cpt_code,
                    "paid_amount": line.paid_amount,
                    "allowed_amount": allowed,
                    "overpayment": round(overpayment, 2),
                })

        if violating_lines:
            results.append(DetectorResult(
                detector_code=self.code,
                finding_type="FEE_SCHEDULE_OVERPAYMENT",
                description=(
                    f"Paid amount exceeds fee schedule (±5% tolerance) for "
                    f"{len(violating_lines)} line(s). Total overpayment: ${total_overpayment:.2f}."
                ),
                overpayment_amount=round(total_overpayment, 2),
                confidence_score=0.85,
                evidence={
                    "lob": claim.lob,
                    "violating_lines": violating_lines,
                    "total_overpayment": round(total_overpayment, 2),
                },
            ))

        return results
