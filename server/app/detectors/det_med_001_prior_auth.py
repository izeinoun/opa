import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim
from ..models.reference import CptPriorAuthRequirement

logger = logging.getLogger(__name__)


class PriorAuthRequiredDetector(BaseDetector):
    """MED-001 — Prior Authorization Required.

    Checks whether procedures that require prior authorization have a valid
    authorization number on the claim or in ClearLink.

    Three outcomes per CPT:
      1. Auth number present on claim              → no finding (clean)
      2. No auth on claim; ClearLink has approved  → LOW  PRIOR_AUTH_NOT_SUBMITTED
         (provider obtained auth but forgot to put the number on the claim)
      3. No auth on claim; ClearLink has pending   → MEDIUM PRIOR_AUTH_NOT_APPROVED
      4. No auth on claim; nothing in ClearLink    → HIGH MISSING_PRIOR_AUTH
    """

    code = "MED-001"
    name = "Prior Authorization Required"
    fwa_rule_code = None

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        logger.info(f"[MED-001] run() called for claim {claim.claim_id}")
        results: List[DetectorResult] = []
        lines = claim.lines or []
        if not lines:
            return results

        claim_cpts = {line.cpt_code for line in lines}

        res = await db_session.execute(
            select(CptPriorAuthRequirement).where(
                CptPriorAuthRequirement.cpt_code.in_(claim_cpts),
                CptPriorAuthRequirement.is_active == True,
            )
        )
        required_rows = res.scalars().all()

        if not required_rows:
            return results

        # Resolve member_number for ClearLink queries (cross-system business key).
        member_number: Optional[str] = None
        if claim.member_id:
            member_number = await self.resolve_member_number(claim.member_id, db_session)

        auth_on_claim = bool(claim.authorization_number and claim.authorization_number.strip())

        for req in required_rows:
            # LOB-specific requirement: skip if it targets a different LOB.
            if req.lob and claim.lob and req.lob.lower() != claim.lob.lower():
                continue

            cpt_code = req.cpt_code
            affected_lines = [l for l in lines if l.cpt_code == cpt_code]
            overpayment = round(sum((l.paid_amount or 0.0) for l in affected_lines), 2)

            if auth_on_claim:
                logger.debug(
                    f"[MED-001] CPT {cpt_code}: auth number '{claim.authorization_number}' "
                    "present on claim — no finding"
                )
                continue

            # No auth number on claim — query ClearLink.
            pa: dict = {"found": False, "approved": False}
            if member_number:
                try:
                    from .clearlink_detector_helper import search_clearlink_for_prior_auth
                    pa = await search_clearlink_for_prior_auth(
                        member_number, cpt_code, claim.service_from_date
                    )
                except Exception as e:
                    logger.warning(f"[MED-001] ClearLink lookup failed for CPT {cpt_code}: {e}")

            if pa["found"] and pa["approved"]:
                description = (
                    f"CPT {cpt_code} ({req.description}) requires prior authorization per "
                    f"{req.source}. No authorization number was submitted on the claim, however "
                    f"a matching prior authorization was found in ClearLink "
                    f"(PA ID: {pa['auth_id']}, status: {pa['status']}"
                    f"{', approved: ' + pa['decided_at'] if pa['decided_at'] else ''}). "
                    f"The provider appears to have obtained the authorization but failed to include "
                    f"the authorization number on the claim form. Submit a corrected claim with the "
                    f"authorization number to clear this finding."
                )
                results.append(DetectorResult(
                    detector_code=self.code,
                    finding_type="PRIOR_AUTH_NOT_SUBMITTED",
                    description=description,
                    overpayment_amount=0.0,
                    confidence_score=0.70,
                    evidence={
                        "cpt_code": cpt_code,
                        "auth_required": True,
                        "auth_on_claim": False,
                        "clearlink_found": True,
                        "clearlink_approved": True,
                        "clearlink_auth_id": pa["auth_id"],
                        "clearlink_status": pa["status"],
                        "clearlink_cpt_codes": pa["cpt_codes"],
                        "clearlink_service_date": pa["service_date"],
                        "clearlink_decided_at": pa["decided_at"],
                        "clearlink_provider": pa["provider_name"],
                        "source": req.source,
                        "affected_line_ids": [l.claim_line_id for l in affected_lines],
                    },
                ))
                logger.info(
                    f"[MED-001] CPT {cpt_code}: auth found in ClearLink (approved) "
                    "but not submitted on claim — LOW finding"
                )

            elif pa["found"] and not pa["approved"]:
                description = (
                    f"CPT {cpt_code} ({req.description}) requires prior authorization per "
                    f"{req.source}. No authorization number was submitted on the claim. "
                    f"A prior authorization request was found in ClearLink "
                    f"(PA ID: {pa['auth_id']}, status: {pa['status']}), but it has not been approved. "
                    f"Payment should be withheld pending a final authorization decision."
                )
                results.append(DetectorResult(
                    detector_code=self.code,
                    finding_type="PRIOR_AUTH_NOT_APPROVED",
                    description=description,
                    overpayment_amount=overpayment,
                    confidence_score=0.80,
                    evidence={
                        "cpt_code": cpt_code,
                        "auth_required": True,
                        "auth_on_claim": False,
                        "clearlink_found": True,
                        "clearlink_approved": False,
                        "clearlink_auth_id": pa["auth_id"],
                        "clearlink_status": pa["status"],
                        "clearlink_cpt_codes": pa["cpt_codes"],
                        "source": req.source,
                        "overpayment": overpayment,
                        "affected_line_ids": [l.claim_line_id for l in affected_lines],
                    },
                ))
                logger.info(
                    f"[MED-001] CPT {cpt_code}: auth found in ClearLink "
                    f"(status={pa['status']}) but not approved — MEDIUM finding"
                )

            else:
                clearlink_note = (
                    " ClearLink was queried and no authorization record was found for this member."
                    if member_number else
                    " ClearLink was not available to cross-check for an existing authorization."
                )
                description = (
                    f"CPT {cpt_code} ({req.description}) requires prior authorization per "
                    f"{req.source}. No authorization number was submitted on the claim.{clearlink_note} "
                    f"This claim may not be payable without a valid prior authorization. "
                    f"Contact the provider to obtain the authorization number or initiate a retro-auth request."
                )
                results.append(DetectorResult(
                    detector_code=self.code,
                    finding_type="MISSING_PRIOR_AUTH",
                    description=description,
                    overpayment_amount=overpayment,
                    confidence_score=0.85,
                    evidence={
                        "cpt_code": cpt_code,
                        "auth_required": True,
                        "auth_on_claim": False,
                        "clearlink_found": False,
                        "clearlink_queried": bool(member_number),
                        "source": req.source,
                        "overpayment": overpayment,
                        "affected_line_ids": [l.claim_line_id for l in affected_lines],
                    },
                ))
                logger.info(
                    f"[MED-001] CPT {cpt_code}: no auth on claim, none in ClearLink — HIGH finding"
                )

        return results
