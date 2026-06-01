from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim, ClaimLine


class DuplicateBillingDetector(BaseDetector):
    code = "DET-01"
    name = "Duplicate Billing Detector"
    # FWA-06 covers the intentional-pattern interpretation of duplicate
    # billing. Every hit gets stamped; downstream review distinguishes a
    # one-off coding error from a fraud pattern.
    fwa_rule_code = "FWA-06"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        results = []

        stmt = (
            select(Claim)
            .where(
                Claim.member_id == claim.member_id,
                Claim.rendering_provider_npi == claim.rendering_provider_npi,
                Claim.service_from_date == claim.service_from_date,
                Claim.claim_id != claim.claim_id,
            )
        )
        result = await db_session.execute(stmt)
        duplicate_claims = result.scalars().all()

        for dup in duplicate_claims:
            claim_cpts = {line.cpt_code for line in (claim.lines or [])}

            dup_lines_res = await db_session.execute(
                select(ClaimLine).where(ClaimLine.claim_id == dup.claim_id)
            )
            dup_lines = dup_lines_res.scalars().all()
            dup_cpts = {line.cpt_code for line in dup_lines}

            if not claim_cpts or not dup_cpts:
                continue

            overlap = claim_cpts & dup_cpts
            if overlap == claim_cpts == dup_cpts:
                confidence = 0.95
                overpayment = min(claim.total_paid, dup.total_paid)
                results.append(DetectorResult(
                    detector_code=self.code,
                    finding_type="DUPLICATE_CLAIM",
                    description=(
                        f"Exact duplicate billing: claim {dup.icn} has same member, "
                        f"provider NPI, CPT codes, and service date."
                    ),
                    overpayment_amount=overpayment,
                    confidence_score=confidence,
                    evidence={
                        "duplicate_claim_id": dup.claim_id,
                        "duplicate_icn": dup.icn,
                        "overlapping_cpts": list(overlap),
                        "original_paid": claim.total_paid,
                        "duplicate_paid": dup.total_paid,
                    },
                ))
            elif overlap:
                confidence = 0.75
                overlap_paid = sum(
                    line.paid_amount
                    for line in (claim.lines or [])
                    if line.cpt_code in overlap
                )
                results.append(DetectorResult(
                    detector_code=self.code,
                    finding_type="DUPLICATE_CLAIM",
                    description=(
                        f"Partial duplicate billing: claim {dup.icn} shares CPT codes "
                        f"{list(overlap)} on the same service date."
                    ),
                    overpayment_amount=overlap_paid,
                    confidence_score=confidence,
                    evidence={
                        "duplicate_claim_id": dup.claim_id,
                        "duplicate_icn": dup.icn,
                        "overlapping_cpts": list(overlap),
                        "overlap_paid": overlap_paid,
                    },
                ))

        return results
