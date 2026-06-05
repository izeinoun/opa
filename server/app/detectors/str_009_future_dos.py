from datetime import date
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim


def _parse_date(value: str | None) -> date | None:
    if not value or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


class FutureDOSDetector(BaseDetector):
    code = "STR-009"
    name = "DOS in Future"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        service_date = _parse_date(claim.service_from_date)
        if service_date is None:
            # Unparseable date — STR-008 (Missing DOS) covers the blank case.
            return []

        receipt_date = _parse_date(claim.submission_date) or date.today()

        if service_date <= receipt_date:
            return []

        days_ahead = (service_date - receipt_date).days
        return [DetectorResult(
            detector_code=self.code,
            finding_type="FUTURE_DOS",
            description=(
                f"Date of service ({claim.service_from_date}) is {days_ahead} day(s) "
                f"after the claim receipt date ({claim.submission_date}). "
                "Future-dated services cannot be adjudicated."
            ),
            overpayment_amount=0.0,
            confidence_score=0.90,
            evidence={
                "service_from_date": claim.service_from_date,
                "submission_date": claim.submission_date,
                "days_in_future": days_ahead,
            },
        )]
