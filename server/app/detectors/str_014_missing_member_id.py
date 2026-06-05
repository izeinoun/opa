from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim

_EMPTY_SENTINELS = {"", "null", "none", "n/a", "unknown"}


def _is_blank(value: str | None) -> bool:
    if value is None:
        return True
    return value.strip().lower() in _EMPTY_SENTINELS


class MissingMemberIDDetector(BaseDetector):
    code = "STR-014"
    name = "Missing Member ID"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        # Check the raw member number from the submitted document (Box 1a on
        # CMS-1500, FL 60 on UB-04), not the resolved member record.
        member_number = claim.submitted_member_number
        if not _is_blank(member_number):
            return []

        return [DetectorResult(
            detector_code=self.code,
            finding_type="MISSING_MEMBER_ID",
            description=(
                "Submitted claim contains no payer-assigned member identifier "
                "(CMS-1500 Box 1a / UB-04 FL 60). "
                "Member ID is required to link the claim to an eligibility record."
            ),
            overpayment_amount=0.0,
            confidence_score=0.95,
            evidence={
                "submitted_member_number": member_number,
                "member_id": claim.member_id,
            },
        )]
