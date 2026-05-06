from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim


class RetroEligibilityDetector(BaseDetector):
    code = "DET-02"
    name = "Eligibility / Coverage Verification"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        results = []
        member = claim.member

        if member is None:
            return results

        # Check A — LOB mismatch
        if member.lob and claim.lob and member.lob.lower() != claim.lob.lower():
            results.append(DetectorResult(
                detector_code=self.code,
                finding_type="CROSS_LOB_MISMATCH",
                description=(
                    f"Member {member.member_number} is enrolled under '{member.lob}' but "
                    f"this claim was billed under '{claim.lob}'. Potential eligibility mismatch."
                ),
                overpayment_amount=claim.total_paid,
                confidence_score=0.80,
                evidence={
                    "member_id": member.member_id,
                    "member_lob": member.lob,
                    "claim_lob": claim.lob,
                    "claim_icn": claim.icn,
                    "total_paid": claim.total_paid,
                },
            ))

        # Check B — Coverage date validation
        if member.coverage_effective_date and claim.service_from_date:
            if claim.service_from_date < member.coverage_effective_date:
                results.append(DetectorResult(
                    detector_code=self.code,
                    finding_type="COVERAGE_NOT_YET_ACTIVE",
                    description=(
                        f"Service date {claim.service_from_date} is before member "
                        f"{member.member_number}'s plan start date "
                        f"{member.coverage_effective_date}. Coverage was not yet active."
                    ),
                    overpayment_amount=claim.total_paid,
                    confidence_score=0.95,
                    evidence={
                        "member_number": member.member_number,
                        "service_date": claim.service_from_date,
                        "plan_start_date": member.coverage_effective_date,
                        "total_paid": claim.total_paid,
                    },
                ))

        if member.coverage_termination_date and claim.service_from_date:
            if claim.service_from_date > member.coverage_termination_date:
                results.append(DetectorResult(
                    detector_code=self.code,
                    finding_type="COVERAGE_TERMINATED",
                    description=(
                        f"Service date {claim.service_from_date} is after member "
                        f"{member.member_number}'s plan termination date "
                        f"{member.coverage_termination_date}. Coverage was no longer active."
                    ),
                    overpayment_amount=claim.total_paid,
                    confidence_score=0.95,
                    evidence={
                        "member_number": member.member_number,
                        "service_date": claim.service_from_date,
                        "plan_start_date": member.coverage_effective_date,
                        "total_paid": claim.total_paid,
                    },
                ))

        return results
