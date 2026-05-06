from typing import List, Dict
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from .det_01_duplicate import DuplicateBillingDetector
from .det_02_retro_eligibility import RetroEligibilityDetector
from .det_04_fee_schedule import FeeScheduleDetector
from .det_06_ncci_mue import NCCIMUEDetector
from .det_08_excluded_provider import ExcludedProviderDetector
from .det_09_coding_errors import CodingErrorDetector


class DetectorOrchestrator:
    def __init__(self) -> None:
        detectors: List[BaseDetector] = [
            DuplicateBillingDetector(),
            RetroEligibilityDetector(),
            FeeScheduleDetector(),
            NCCIMUEDetector(),
            ExcludedProviderDetector(),
            CodingErrorDetector(),
        ]
        self._detectors: Dict[str, BaseDetector] = {d.code: d for d in detectors}

    async def run_all(self, claim, db_session: AsyncSession) -> List[DetectorResult]:
        results = []
        for detector in self._detectors.values():
            try:
                findings = await detector.run(claim, db_session)
                results.extend(findings)
            except Exception as e:
                # Log but don't fail the whole run
                import logging
                logging.getLogger(__name__).error(
                    f"Detector {detector.code} failed: {e}", exc_info=True
                )
        return results

    async def run_by_code(
        self, code: str, claim, db_session: AsyncSession
    ) -> List[DetectorResult]:
        detector = self._detectors.get(code)
        if detector is None:
            raise ValueError(f"Unknown detector code: {code}")
        return await detector.run(claim, db_session)
