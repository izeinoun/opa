import logging
import re
from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim
from ..dao.fee_schedule_dao import FeeScheduleDAO
from ..models.workflow import Document

logger = logging.getLogger(__name__)
TOLERANCE = 0.05


class FeeScheduleDetector(BaseDetector):
    code = "DET-04"
    name = "Fee Schedule Variance Detector"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        results = []
        fee_dao = FeeScheduleDAO(db_session)

        total_overpayment = 0.0
        violating_lines = []

        for line in (claim.lines or []):
            allowed = await fee_dao.get_allowed_amount(
                cpt_code=line.cpt_code,
                lob=claim.lob,
                service_date=claim.service_from_date,
            )
            if allowed is None:
                continue

            threshold = allowed * (1.0 + TOLERANCE)
            if line.paid_amount > threshold:
                overpayment = line.paid_amount - allowed
                total_overpayment += overpayment
                violating_lines.append({
                    "line_id": line.claim_line_id,
                    "line_number": line.line_number,
                    "cpt_code": line.cpt_code,
                    "paid_amount": line.paid_amount,
                    "allowed_amount": allowed,
                    "overpayment": round(overpayment, 2),
                })

        if violating_lines:
            # ── Check for prior authorization approving higher amounts ──────────
            # First check attached documents, then fall back to ClearLink
            has_auth_approval = await self._check_for_auth_approval(claim, db_session)

            if not has_auth_approval and claim.member_id:
                # Check ClearLink if not found in attached documents. ClearLink
                # resolves members by member_number (not OPA's UUID), so translate.
                member_number = await self.resolve_member_number(claim.member_id, db_session)
                if member_number:
                    has_auth_approval = await self._check_clearlink_for_auth(member_number, claim.lines)
                    if has_auth_approval:
                        logger.info(f"[DET-04] Prior auth found in ClearLink for member {member_number}")

            confidence = 0.85
            description = (
                f"Paid amount exceeds fee schedule (±5% tolerance) for "
                f"{len(violating_lines)} line(s). Total overpayment: ${total_overpayment:.2f}."
            )

            if has_auth_approval:
                confidence = 0.45  # Reduce confidence if authorization found
                description += " However, prior authorization document found approving higher amount — may be justified."
                logger.info(f"[DET-04] Reduced confidence for fee schedule variance — prior auth approval found")

            results.append(DetectorResult(
                detector_code=self.code,
                finding_type="FEE_SCHEDULE_OVERPAYMENT",
                description=description,
                overpayment_amount=round(total_overpayment, 2),
                confidence_score=confidence,
                evidence={
                    "lob": claim.lob,
                    "violating_lines": violating_lines,
                    "total_overpayment": round(total_overpayment, 2),
                    "has_auth_approval": has_auth_approval,
                },
            ))

        return results

    # ── Document helpers ──────────────────────────────────────────────────────

    async def _check_for_auth_approval(self, claim: Claim, db_session: AsyncSession) -> bool:
        """Search attached prior auth documents for approval of the specific CPT codes on this claim.

        Returns True only if:
        1. Document is identified as prior authorization
        2. CPT code(s) in document match the claim's CPT code(s)

        This works for both PayGuard (post-pay) and ClaimGuard (pre-pay) pipelines.
        """
        claim_cpts = {line.cpt_code for line in (claim.lines or [])}
        if not claim_cpts:
            return False

        # Query documents linked to case or claim
        from sqlalchemy import or_
        from app.models.workflow import OpaCase

        # Find the case associated with this claim
        case_result = await db_session.execute(
            select(OpaCase).where(OpaCase.claim_id == claim.claim_id)
        )
        case = case_result.scalar_one_or_none()

        # Query documents linked to either the case or the claim
        doc_filter = []
        if case and case.case_id:
            doc_filter.append(Document.case_id == case.case_id)
        if claim.claim_id:
            doc_filter.append(Document.claim_id == claim.claim_id)

        if not doc_filter:
            return False

        result = await db_session.execute(
            select(Document).where(or_(*doc_filter))
        )
        documents = result.scalars().all()

        # Keywords indicating a prior authorization document
        auth_keywords = [
            r"prior\s+auth",
            r"authorization",
            r"pre.*approval",
            r"pre-certification",
            r"auth.*approval",
        ]
        auth_pattern = re.compile("|".join(auth_keywords), re.IGNORECASE)

        # CPT/HCPCS code pattern: 5 digits or letter + 4 digits
        cpt_pattern = re.compile(r'\b([A-Z]?\d{4,5})\b')

        for doc in documents:
            if not doc.extracted_text:
                continue

            # First, verify this is a prior auth document
            if not auth_pattern.search(doc.extracted_text):
                continue

            logger.debug(f"[DET-04] Found prior auth document: {doc.filename}")

            # Extract all CPT/HCPCS codes from the document
            extracted_cpts = set(cpt_pattern.findall(doc.extracted_text))
            logger.debug(f"[DET-04] CPT codes found in document: {extracted_cpts}")
            logger.debug(f"[DET-04] CPT codes on claim: {claim_cpts}")

            # Check if ANY claim CPT appears in the prior auth document
            matching_cpts = claim_cpts.intersection(extracted_cpts)
            if matching_cpts:
                logger.info(
                    f"[DET-04] Prior auth found with matching CPT code(s): {matching_cpts} "
                    f"(document: {doc.filename})"
                )
                return True
            else:
                logger.debug(
                    f"[DET-04] Prior auth found but CPT codes don't match. "
                    f"Auth has {extracted_cpts}, claim has {claim_cpts}"
                )

        return False

    async def _check_clearlink_for_auth(self, member_id: str, lines: list) -> bool:
        """Query ClearLink for prior authorizations matching claim CPT codes.

        Returns True if any claim CPT found in member's ClearLink authorizations.
        Safe to call even if ClearLink is not configured (returns False).
        """
        if not member_id or not lines:
            return False

        try:
            from .clearlink_detector_helper import search_clearlink_for_prior_auth

            # Check each CPT code on the claim
            for line in lines:
                cpt_code = line.cpt_code
                found = await search_clearlink_for_prior_auth(member_id, cpt_code)
                if found:
                    logger.info(f"[DET-04] Found prior auth in ClearLink for CPT {cpt_code}")
                    return True

            return False

        except ImportError:
            logger.debug("[DET-04] ClearLink detector helper not available")
            return False
        except Exception as e:
            logger.warning(f"[DET-04] Error querying ClearLink for prior auth: {e}")
            return False
