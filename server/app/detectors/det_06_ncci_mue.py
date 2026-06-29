import logging
import re
from typing import List, Set, Tuple
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim
from ..models.workflow import Document

logger = logging.getLogger(__name__)

NCCI_MUTUALLY_EXCLUSIVE_PAIRS: Set[Tuple[str, str]] = {
    ("99213", "99214"),
    ("27447", "27130"),
    ("43239", "43235"),
    ("70553", "70551"),
    ("93306", "93307"),
    ("99232", "99233"),
    ("36415", "36416"),
    ("20610", "20600"),
    ("97110", "97112"),
    ("11042", "11043"),
}

MUE_LIMITS = {
    "99213": 1, "99214": 1, "36415": 1, "93306": 1,
    "27447": 1, "70553": 1, "43239": 1, "97110": 4,
    "20610": 3, "11042": 1,
}


class NCCIMUEDetector(BaseDetector):
    code = "DET-06"
    name = "NCCI/MUE Violation Detector"
    # FWA-05 (unbundling) — NCCI mutually-exclusive pairs and MUE breaches
    # are the deterministic mechanism for catching unbundling patterns.
    fwa_rule_code = "FWA-05"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        results = []
        lines = claim.lines or []
        if not lines:
            return results

        cpt_set = {line.cpt_code for line in lines}

        for (cpt_a, cpt_b) in NCCI_MUTUALLY_EXCLUSIVE_PAIRS:
            if cpt_a in cpt_set and cpt_b in cpt_set:
                paid_a = sum(l.paid_amount for l in lines if l.cpt_code == cpt_a)
                paid_b = sum(l.paid_amount for l in lines if l.cpt_code == cpt_b)

                # ── Check for medical justification in documents ──────────────
                has_justification = await self._check_for_medical_justification(claim, cpt_a, cpt_b, db_session)

                # ── Also check ClearLink for clinical justification ──────────────
                if not has_justification and claim.member_id:
                    member_number = await self.resolve_member_number(claim.member_id, db_session)
                    if member_number:
                        has_justification = await self._check_clearlink_for_medical_justification(
                            member_number, cpt_a, cpt_b
                        )
                        if has_justification:
                            logger.info(f"[DET-06] Medical justification found in ClearLink for {cpt_a} and {cpt_b}")

                confidence = 0.88
                description = f"Mutually exclusive CPT codes billed on same claim: {cpt_a} and {cpt_b}."

                if has_justification:
                    confidence = 0.45  # Reduce confidence if medical justification found
                    description += " However, medical documentation found justifying both procedures."
                    logger.info(f"[DET-06] Reduced confidence for NCCI violation — medical justification found")

                results.append(DetectorResult(
                    detector_code=self.code,
                    finding_type="NCCI_VIOLATION",
                    description=description,
                    overpayment_amount=round(min(paid_a, paid_b), 2),
                    confidence_score=confidence,
                    evidence={
                        "cpt_code_a": cpt_a,
                        "cpt_code_b": cpt_b,
                        "paid_a": paid_a,
                        "paid_b": paid_b,
                        "claim_id": claim.claim_id,
                        "has_justification": has_justification,
                    },
                ))

        for line in lines:
            limit = MUE_LIMITS.get(line.cpt_code)
            if limit is not None and line.units_billed > limit:
                excess = line.units_billed - limit
                overpayment = round(line.paid_amount * (excess / line.units_billed), 2)
                results.append(DetectorResult(
                    detector_code=self.code,
                    finding_type="MUE_EXCEEDED",
                    description=(
                        f"CPT {line.cpt_code} billed with {line.units_billed} units, "
                        f"exceeding MUE limit of {limit}."
                    ),
                    overpayment_amount=overpayment,
                    confidence_score=0.88,
                    evidence={
                        "line_id": line.claim_line_id,
                        "cpt_code": line.cpt_code,
                        "billed_units": line.units_billed,
                        "mue_limit": limit,
                        "excess_units": excess,
                        "paid_amount": line.paid_amount,
                    },
                ))

        return results

    # ── Document helpers ──────────────────────────────────────────────────────

    async def _check_for_medical_justification(
        self, claim: Claim, cpt_a: str, cpt_b: str, db_session: AsyncSession
    ) -> bool:
        """Search attached medical documents for justification of mutually exclusive CPT codes.

        Returns True only if:
        1. Document contains medical justification keywords
        2. Document mentions BOTH of the mutually-exclusive CPT codes

        This ensures the justification is specifically for this pair of procedures.
        Works for both PayGuard (post-pay) and ClaimGuard (pre-pay) pipelines.
        """
        # Query documents linked to case or claim
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

        # Keywords indicating medical justification for procedures
        justification_keywords = [
            r"separate\s+(procedures?|sessions?|occasions?)",
            r"different\s+(times?|locations?|sessions?)",
            r"both\s+necessary",
            r"both\s+performed",
            r"each\s+procedure",
            r"medically\s+necessary",
            r"clinically\s+indicated",
            r"separate\s+indications?",
        ]
        justification_pattern = re.compile("|".join(justification_keywords), re.IGNORECASE)

        for doc in documents:
            if not doc.extracted_text:
                continue

            # First, check if document contains justification keywords
            if not justification_pattern.search(doc.extracted_text):
                continue

            logger.debug(f"[DET-06] Found medical justification keywords in {doc.filename}")

            # Now verify BOTH specific CPT codes are mentioned in the document
            # (not just any CPT codes, but specifically the mutually-exclusive pair)
            cpt_a_found = re.search(rf'\b{cpt_a}\b', doc.extracted_text)
            cpt_b_found = re.search(rf'\b{cpt_b}\b', doc.extracted_text)

            if cpt_a_found and cpt_b_found:
                logger.info(
                    f"[DET-06] Medical justification found for both CPT {cpt_a} and {cpt_b} "
                    f"in document {doc.filename}"
                )
                return True
            else:
                logger.debug(
                    f"[DET-06] Justification keywords found but CPT codes don't match. "
                    f"Document has: {cpt_a_found and cpt_a} {cpt_b_found and cpt_b}, "
                    f"looking for: {cpt_a} and {cpt_b}"
                )

        return False

    async def _check_clearlink_for_medical_justification(
        self, member_id: str, cpt_a: str, cpt_b: str
    ) -> bool:
        """Query ClearLink clinical notes for medical justification of mutually exclusive procedures.

        Returns True if notes contain keywords indicating both procedures were medically necessary/separate.
        Safe to call even if ClearLink is not configured (returns False).
        """
        if not member_id:
            return False

        try:
            from .clearlink_detector_helper import search_clearlink_for_clinical_notes

            # Keywords indicating justification for both procedures
            keywords = [
                r"separate\s+(procedures?|sessions?|occasions?)",
                r"different\s+(times?|locations?|sessions?)",
                r"both\s+necessary",
                r"both\s+performed",
                r"each\s+procedure",
                r"medically\s+necessary",
                r"clinically\s+indicated",
                r"separate\s+indications?",
            ]

            found = await search_clearlink_for_clinical_notes(member_id, keywords)
            if found:
                logger.info(f"[DET-06] Medical justification found in ClearLink clinical notes")
            return found

        except ImportError:
            logger.debug("[DET-06] ClearLink detector helper not available")
            return False
        except Exception as e:
            logger.warning(f"[DET-06] Error querying ClearLink: {e}")
            return False
