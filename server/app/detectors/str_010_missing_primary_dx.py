from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim

_EMPTY_SENTINELS = {"", "null", "none", "n/a", "unknown"}


def _is_blank(value: str | None) -> bool:
    if value is None:
        return True
    return value.strip().lower() in _EMPTY_SENTINELS


class MissingPrimaryDxDetector(BaseDetector):
    code = "STR-010"
    name = "Missing Primary Diagnosis"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        if not _is_blank(claim.primary_icd):
            return []

        return [DetectorResult(
            detector_code=self.code,
            finding_type="MISSING_PRIMARY_DX",
            description=(
                "Claim is missing a primary ICD-10 diagnosis code. "
                "At least one diagnosis is required for adjudication."
            ),
            overpayment_amount=0.0,
            confidence_score=0.95,
            evidence={
                "primary_icd": claim.primary_icd,
            },
        )]
