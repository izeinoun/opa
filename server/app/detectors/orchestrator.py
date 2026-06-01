from typing import List, Dict, Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from .det_01_duplicate import DuplicateBillingDetector
from .det_02_retro_eligibility import RetroEligibilityDetector
from .det_04_fee_schedule import FeeScheduleDetector
from .det_06_ncci_mue import NCCIMUEDetector
from .det_08_excluded_provider import ExcludedProviderDetector
from .det_09_coding_errors import CodingErrorDetector
from .fwa_02_credential_mismatch import CredentialMismatchDetector
from .fwa_03_pos_mismatch import POSMismatchDetector


class DetectorOrchestrator:
    def __init__(self) -> None:
        detectors: List[BaseDetector] = [
            DuplicateBillingDetector(),
            RetroEligibilityDetector(),
            FeeScheduleDetector(),
            NCCIMUEDetector(),
            ExcludedProviderDetector(),
            CodingErrorDetector(),
            # Deterministic FWA rules — FWA-04 + FWA-07 are LLM-assisted and
            # live in services/fwa_service.py, called from the analyze paths.
            CredentialMismatchDetector(),
            POSMismatchDetector(),
        ]
        self._detectors: Dict[str, BaseDetector] = {d.code: d for d in detectors}

    async def run_all(
        self,
        claim,
        db_session: AsyncSession,
        enabled_codes: Optional[Set[str]] = None,
        score_multipliers: Optional[Dict[str, float]] = None,
    ) -> List[DetectorResult]:
        """Run enabled detectors. score_multipliers scales each finding's confidence_score."""
        results = []
        for detector in self._detectors.values():
            if enabled_codes is not None and detector.code not in enabled_codes:
                continue
            try:
                findings = await detector.run(claim, db_session)
                # Stamp the detector's FWA mapping onto every result so the
                # downstream Finding persistence picks up `fwa_indicator`
                # and `fwa_rule_code` without each detector having to set
                # them on every DetectorResult it constructs.
                if detector.fwa_rule_code:
                    for f in findings:
                        if not f.fwa_rule_code:   # per-result override wins
                            f.fwa_rule_code = detector.fwa_rule_code
                            f.fwa_indicator = True
                if score_multipliers is not None:
                    mult = score_multipliers.get(detector.code, 1.0)
                    if mult != 1.0:
                        for f in findings:
                            f.confidence_score = max(0.0, min(1.0, f.confidence_score * mult))
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
