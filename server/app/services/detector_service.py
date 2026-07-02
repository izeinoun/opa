from typing import Callable, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..detectors.orchestrator import DetectorOrchestrator
from ..dao.finding_dao import FindingDAO
from ..dao.claim_dao import ClaimDAO
from ..models.workflow import OpaCase, LikelihoodScore
from ..models.claims import Claim
from . import detector_rule_service


# Detectors that reason over diagnoses. Deferred while a claim is dx_pending
# (created from an 835, awaiting its 837), so they don't fire against the
# placeholder primary_icd. Re-run in full once the 837 supplies real Dx.
DX_DEPENDENT_CODES = {"DET-09", "DET-13", "DET-18", "DET-19", "STR-010"}


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
        progress_cb: Optional[Callable[[int, int, Optional[str]], None]] = None,
    ) -> dict:
        """Run detectors against the case's claim. Replaces existing findings.

        pipeline_mode drives which rules are eligible: get_runtime_config gates
        on both the structural prepay/postpay catalog flag and the operator
        enabled_prepay/enabled_postpay toggle, so only rules valid for the
        pipeline and switched on by the admin will fire.

        progress_cb(completed, total, current_label) is forwarded to the
        orchestrator for the live rerun-progress modal (see run_all).
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

        effective_pipeline = pipeline_mode or claim.pipeline_mode
        enabled_codes, multipliers = await detector_rule_service.get_runtime_config(
            self.session, effective_pipeline
        )
        # Defer diagnosis-dependent rules while the claim awaits its 837 (no Dx
        # yet). They run on the post-link re-evaluation once real Dx are present.
        if getattr(claim, "dx_pending", False):
            enabled_codes = enabled_codes - DX_DEPENDENT_CODES

        # Run detectors FIRST — this is the slow part (ClearLink round-trips +
        # LLM calls). Deliberately BEFORE any write so we don't hold a SQLite
        # write transaction open across that I/O (which serializes the whole
        # single-worker app). The delete+insert below is then a tight block.
        results = await self.orchestrator.run_all(
            claim, self.session,
            enabled_codes=enabled_codes,
            score_multipliers=multipliers,
            progress_cb=progress_cb,
        )

        # Clear old findings for this case, then insert the fresh pass.
        await self.finding_dao.delete_by_case(case.case_id)

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
                severity=getattr(r, "severity", None),
            )
            new_findings.append(finding)
            # Phase 2: seed default disposition (accepted / needs_review / rejected)
            await ensure_disposition(self.session, finding, case.case_id)

        # Recompute likelihood score from detector outputs
        await self._update_likelihood(case, claim, new_findings)

        # Pre-pay only: write a short, claim-specific plain-English explanation
        # onto each fired finding (findings.issue_summary) via the fast model,
        # for the PayGuard-style card in ClaimGuard. Gated by ai_suggestions_enabled
        # and fully exception-safe — never blocks detection.
        if effective_pipeline == "pre_pay" and new_findings:
            from .finding_explanation_service import generate_for_findings
            try:
                await generate_for_findings(self.session, claim, new_findings)
            except Exception:  # belt-and-suspenders; the service also guards
                pass

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
