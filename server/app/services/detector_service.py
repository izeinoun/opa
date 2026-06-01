from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..detectors.orchestrator import DetectorOrchestrator
from ..dao.finding_dao import FindingDAO
from ..dao.claim_dao import ClaimDAO
from ..models.workflow import OpaCase, LikelihoodScore
from ..models.claims import Claim
from . import detector_rule_service


# CPT risk lookup (mirrors seed_cases)
_CPT_RISK = {
    "99213": 0.10, "99214": 0.20, "99215": 0.30, "99232": 0.35,
    "93000": 0.15, "93306": 0.40, "93458": 0.70, "27447": 0.65,
    "29881": 0.55, "97110": 0.25, "97530": 0.30, "70553": 0.35,
    "72148": 0.25, "99285": 0.45, "99291": 0.60,
}


class DetectorService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.orchestrator = DetectorOrchestrator()
        self.finding_dao = FindingDAO(session)
        self.claim_dao = ClaimDAO(session)

    async def run_for_case(
        self,
        case_sequence: int,
        *,
        pipeline_mode: str | None = None,
    ) -> dict:
        """Run detectors against the case's claim. Replaces existing findings.

        When `pipeline_mode == 'pre_pay'`, the enabled-code set is intersected
        with `PREPAY_SAFE_CODES` so detectors that need payment data (DET-04
        fee schedule) are skipped silently — they'd produce nothing anyway,
        but skipping avoids noisy "no paid amount" errors in logs.
        """
        case_res = await self.session.execute(
            select(OpaCase).where(OpaCase.case_sequence == case_sequence)
        )
        case = case_res.scalar_one_or_none()
        if case is None:
            raise ValueError(f"Case {case_sequence} not found")

        claim = await self.claim_dao.get_with_details(case.claim_id)
        if claim is None:
            raise ValueError(f"Claim {case.claim_id} not found")

        # Clear old findings for this case before inserting fresh ones
        await self.finding_dao.delete_by_case(case.case_id)

        enabled_codes, multipliers = await detector_rule_service.get_runtime_config(self.session)
        # Pipeline filter — intersect with safe-for-pre-pay set when the
        # claim is in the pre-pay pipeline. Caller is responsible for
        # passing pipeline_mode; we fall back to claim.pipeline_mode for
        # safety so this works correctly even if the caller forgets.
        effective_pipeline = pipeline_mode or claim.pipeline_mode
        if effective_pipeline == "pre_pay":
            enabled_codes = enabled_codes & detector_rule_service.PREPAY_SAFE_CODES
        results = await self.orchestrator.run_all(
            claim, self.session,
            enabled_codes=enabled_codes,
            score_multipliers=multipliers,
        )

        from .disposition_service import ensure_disposition

        new_findings = []
        for r in results:
            finding = await self.finding_dao.create_finding(
                claim_id=case.claim_id,
                case_id=case.case_id,
                detector_code=r.detector_code,
                finding_type=r.finding_type,
                description=r.description,
                overpayment_amount=r.overpayment_amount,
                confidence_score=r.confidence_score,
                evidence_json=r.evidence,
                fwa_indicator=r.fwa_indicator,
                fwa_rule_code=r.fwa_rule_code,
            )
            new_findings.append(finding)
            # Phase 2: seed default disposition (accepted / needs_review / rejected)
            await ensure_disposition(self.session, finding, case.case_id)

        # Recompute likelihood score from detector outputs
        await self._update_likelihood(case, claim, new_findings)

        await self.session.commit()

        return {
            "case_sequence": case_sequence,
            "detectors_run": len(self.orchestrator._detectors),
            "findings_created": len(new_findings),
            "findings": [
                {
                    "detector": f.detector_id,
                    "severity": f.severity,
                    "confidence": f.confidence,
                    "overpayment": f.overpayment_amount,
                }
                for f in new_findings
            ],
        }

    async def _update_likelihood(self, case: OpaCase, claim: Claim, findings: list) -> None:
        # Likelihood = billing_variance_score from the ML model directly
        bv_score = 0.30
        if claim.provider_org and claim.provider_org.providers:
            provider = next(
                (p for p in claim.provider_org.providers if p.npi == claim.rendering_provider_npi),
                claim.provider_org.providers[0],
            )
            bv_score = provider.billing_variance_score or 0.30

        # Update the existing LikelihoodScore row
        ls_res = await self.session.execute(
            select(LikelihoodScore).where(LikelihoodScore.case_id == case.case_id)
        )
        ls = ls_res.scalar_one_or_none()
        if ls:
            ls.billing_variance_score = round(bv_score, 4)
            ls.composite_likelihood = round(bv_score, 4)
            await self.session.flush()
