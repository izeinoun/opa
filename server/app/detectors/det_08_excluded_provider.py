from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim


class ExcludedProviderDetector(BaseDetector):
    code = "DET-08"
    name = "Excluded Provider Detector"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        results = []

        provider = None
        if claim.provider_org and claim.provider_org.providers:
            for p in claim.provider_org.providers:
                if p.npi == claim.rendering_provider_npi:
                    provider = p
                    break
            if provider is None:
                provider = claim.provider_org.providers[0]

        if provider is None:
            return results

        if provider.is_excluded:
            results.append(DetectorResult(
                detector_code=self.code,
                finding_type="EXCLUDED_PROVIDER",
                description=(
                    f"Rendering provider NPI {provider.npi} ({provider.name}) is flagged as "
                    f"excluded. Source: {provider.exclusion_source or 'OIG exclusion list'}."
                ),
                overpayment_amount=claim.total_paid,
                confidence_score=1.0,
                evidence={
                    "provider_id": provider.provider_id,
                    "provider_npi": provider.npi,
                    "provider_name": provider.name,
                    "exclusion_source": provider.exclusion_source,
                    "exclusion_effective_date": provider.exclusion_effective_date,
                    "total_paid": claim.total_paid,
                },
            ))

        return results
