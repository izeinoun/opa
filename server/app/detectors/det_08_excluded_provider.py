from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim
from ..dao.excluded_provider_dao import ExcludedProviderDAO


class ExcludedProviderDetector(BaseDetector):
    code = "DET-08"
    name = "Excluded Provider Detector"
    # FWA-01 (provider exclusion / OIG-SAM match) — any hit here is fraud
    # by definition. Posterior already hard-codes 0.98 when DET-08 fires.
    fwa_rule_code = "FWA-01"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        results = []

        # Resolve the rendering provider from our own roster by exact NPI match
        # (for naming and the manually-flagged exclusion path). No fallback to
        # an arbitrary org provider — the exclusion decision must key off the
        # actual rendering NPI, never an unrelated colleague in the same org.
        provider = None
        if claim.provider_org and claim.provider_org.providers:
            for p in claim.provider_org.providers:
                if p.npi == claim.rendering_provider_npi:
                    provider = p
                    break

        # Primary screen: match the claim's rendering NPI against the CMS/OIG
        # LEIE reference table. This catches excluded NPIs regardless of whether
        # the provider is in our roster — the realistic exclusion check.
        leie = None
        if claim.rendering_provider_npi:
            leie = await ExcludedProviderDAO(db_session).get_by_npi(
                claim.rendering_provider_npi
            )

        # Secondary path: a roster provider manually flagged as excluded.
        roster_excluded = provider is not None and provider.is_excluded

        if leie is None and not roster_excluded:
            return results

        npi = claim.rendering_provider_npi or (provider.npi if provider else "unknown")
        name = (
            leie.business_name
            or " ".join(filter(None, [leie.first_name, leie.last_name]))
            if leie else None
        ) or (provider.name if provider else "unknown")

        if leie is not None:
            source = f"{leie.source} (statute {leie.exclusion_type})" if leie.exclusion_type else leie.source
            effective_date = leie.exclusion_date
        else:
            source = provider.exclusion_source or "OIG exclusion list"
            effective_date = provider.exclusion_effective_date

        evidence = {
            "provider_npi": npi,
            "provider_name": name,
            "exclusion_source": source,
            "exclusion_effective_date": effective_date,
            "total_paid": claim.total_paid,
            "matched_leie": leie is not None,
        }
        if provider is not None:
            evidence["provider_id"] = provider.provider_id
        if leie is not None:
            evidence["leie_exclusion_type"] = leie.exclusion_type
            evidence["leie_state"] = leie.state

        results.append(DetectorResult(
            detector_code=self.code,
            finding_type="EXCLUDED_PROVIDER",
            description=(
                f"Rendering provider NPI {npi} ({name}) matches an active "
                f"exclusion. Source: {source}."
            ),
            overpayment_amount=claim.total_paid,
            confidence_score=1.0,
            evidence=evidence,
        ))

        return results
