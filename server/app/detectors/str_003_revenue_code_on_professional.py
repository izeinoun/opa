from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim

_PROFESSIONAL_FORM_TYPES = {"CMS-1500", "cms-1500", "1500"}


class RevenueCodeOnProfessionalDetector(BaseDetector):
    code = "STR-003"
    name = "Revenue Code on Professional Claim"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        if claim.claim_form_type not in _PROFESSIONAL_FORM_TYPES:
            return []

        bad_lines = [
            {"line_number": line.line_number, "cpt_code": line.cpt_code, "revenue_code": line.revenue_code}
            for line in (claim.lines or [])
            if (line.revenue_code or "").strip()
        ]
        if not bad_lines:
            return []

        codes = ", ".join(str(l["revenue_code"]) for l in bad_lines)
        return [DetectorResult(
            detector_code=self.code,
            finding_type="REVENUE_CODE_ON_PROFESSIONAL_CLAIM",
            description=(
                f"Revenue code(s) {codes} present on a CMS-1500 professional claim. "
                "Revenue codes are UB-04 institutional fields (FL 42) and must not appear "
                "on professional claims — indicates a form-type mismatch or data entry error."
            ),
            overpayment_amount=0.0,
            confidence_score=0.92,
            evidence={
                "claim_form_type": claim.claim_form_type,
                "affected_lines": bad_lines,
            },
        )]
