from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim

_EMPTY_SENTINELS = {"", "null", "none", "n/a", "unknown", "0000-00-00"}


def _is_blank(value: str | None) -> bool:
    if value is None:
        return True
    return value.strip().lower() in _EMPTY_SENTINELS


class MissingDOBDetector(BaseDetector):
    code = "STR-013"
    name = "Missing Patient DOB"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        # Check the raw DOB from the submitted document, not the resolved
        # member record (which may carry a placeholder value).
        dob = claim.submitted_patient_dob
        if not _is_blank(dob):
            return []

        return [DetectorResult(
            detector_code=self.code,
            finding_type="MISSING_PATIENT_DOB",
            description=(
                "Submitted claim contains no patient date of birth. "
                "DOB is required for age-based coverage and medical necessity edits."
            ),
            overpayment_amount=0.0,
            confidence_score=0.95,
            evidence={
                "submitted_patient_dob": dob,
                "member_id": claim.member_id,
            },
        )]
