from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim

# Values that indicate the field was never populated, regardless of their
# technical non-NULL status. Common OCR / intake artifacts.
_EMPTY_SENTINELS = {"", "null", "none", "n/a", "0000-00-00", "unknown"}


def _is_blank(value: str | None) -> bool:
    if value is None:
        return True
    return value.strip().lower() in _EMPTY_SENTINELS


class MissingDOSDetector(BaseDetector):
    code = "STR-008"
    name = "Missing Date of Service"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        if not _is_blank(claim.service_from_date):
            return []

        return [DetectorResult(
            detector_code=self.code,
            finding_type="MISSING_DOS",
            description=(
                "Claim is missing a date of service. "
                "service_from_date is required for adjudication."
            ),
            overpayment_amount=0.0,
            confidence_score=0.95,
            evidence={
                "service_from_date": claim.service_from_date,
                "service_to_date": claim.service_to_date,
            },
        )]
