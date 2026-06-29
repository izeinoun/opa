import logging
import re
from collections import defaultdict
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from .coverage_gap import record_coverage_gap
from ..models.claims import Claim, line_diag_codes
from ..models.reference import CptDxCoverage
from ..models.workflow import RuntimeConfig, Document, OpaCase

logger = logging.getLogger(__name__)

_CERTAINTY_CONF = {"mandatory": 0.80, "guideline": 0.65, "heuristic": 0.50}


class MedicalNecessityDetector(BaseDetector):
    code = "DET-18"
    name = "Medical Necessity Detector"
    # Medical necessity denials are coverage/clinical determinations, not FWA.
    fwa_rule_code = None

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        logger.info(f"[DET-18] run() called for claim {claim.claim_id}")
        results = []
        lines = claim.lines or []
        if not lines:
            return results

        claim_cpts = {line.cpt_code for line in lines}

        # Collect all ICD codes on the claim (header + per-line).
        all_icds: set[str] = set()
        if claim.primary_icd and claim.primary_icd.strip():
            all_icds.add(claim.primary_icd.strip())
        for line in lines:
            all_icds.update(line_diag_codes(line))

        # ── Search attached medical notes for additional diagnoses ──────────────
        # If the case has supporting medical documents (surgical notes, radiology
        # reports, etc.), extract diagnosis codes from them. This allows DET-18
        # to recognize that a required diagnosis is documented even if it wasn't
        # coded on the original claim.
        document_icds = await self._extract_diagnoses_from_case_documents(claim, db_session)
        all_icds.update(document_icds)
        if document_icds:
            logger.info(f"[DET-18] Found {len(document_icds)} diagnoses in case documents: {document_icds}")

        # ── Also check ClearLink for member's clinical diagnoses ────────────────
        # If ClearLink MCP is configured, query member's medical records for
        # diagnoses. This catches diagnoses documented in external clinical
        # systems but not yet attached to the case.
        if claim.member_id:
            # ClearLink resolves members by member_number (the cross-system business
            # key), not OPA's internal UUID member_id — translate before querying.
            member_number = await self.resolve_member_number(claim.member_id, db_session)
            if member_number:
                clearlink_icds = await self._search_clearlink_for_diagnoses(member_number)
                all_icds.update(clearlink_icds)
                if clearlink_icds:
                    logger.info(f"[DET-18] Found {len(clearlink_icds)} diagnoses from ClearLink: {clearlink_icds}")

        # Pull all required/supporting coverage rules for CPTs on the claim.
        res = await db_session.execute(
            select(CptDxCoverage).where(
                CptDxCoverage.cpt_code.in_(claim_cpts),
                CptDxCoverage.coverage_type.in_(["required", "supporting"]),
            )
        )
        coverage_rows = res.scalars().all()

        # Identify CPTs with no catalogue entries — register a coverage gap for each.
        # When ai_suggestions_enabled is on, the LLM evaluates the uncatalogued CPT
        # and, if it confirms a denial, its finding supersedes the informational gap
        # finding. Gap tracking (DB upsert + audit log) always runs either way.
        catalogued_cpts = {row.cpt_code for row in coverage_rows}
        ai_on = await self._ai_enabled(db_session)
        for cpt_code in sorted(claim_cpts - catalogued_cpts):
            gap_result = await record_coverage_gap(self.code, cpt_code, claim, db_session)
            if ai_on:
                affected = [l for l in lines if l.cpt_code == cpt_code]
                llm_result = await self._try_llm_evaluation(
                    cpt_code, claim, affected, all_icds, db_session
                )
                if llm_result is not None:
                    results.append(llm_result)
                    continue
            results.append(gap_result)

        if not coverage_rows:
            return results

        # Group by CPT: track which types of rules exist and which claim ICDs satisfy them.
        rules_by_cpt: dict[str, dict] = defaultdict(
            lambda: {"required": [], "supporting": [], "matched_required": [], "matched_supporting": []}
        )
        for row in coverage_rows:
            bucket = rules_by_cpt[row.cpt_code]
            bucket[row.coverage_type].append(row)
            if row.icd_code in all_icds:
                bucket[f"matched_{row.coverage_type}"].append(row)

        for cpt_code, bucket in rules_by_cpt.items():
            has_required = bool(bucket["required"])
            matched_required = bucket["matched_required"]
            matched_supporting = bucket["matched_supporting"]

            # A claim ICD satisfies either a required or supporting rule → no finding.
            if matched_required or matched_supporting:
                continue

            affected_lines = [l for l in lines if l.cpt_code == cpt_code]
            overpayment = round(sum((l.paid_amount or 0.0) for l in affected_lines), 2)

            # Pick the best source citation from the required rows (or supporting if none).
            reference_rows = bucket["required"] or bucket["supporting"]
            representative = reference_rows[0]
            source = (
                f"{representative.source_document} ({representative.source_authority})"
                if representative.source_document
                else "LCD/NCD Coverage Policy"
            )

            if has_required:
                # LCD defines explicit required DX codes; none are present.
                required_icds = [r.icd_code for r in bucket["required"]]
                confidence = round(
                    _CERTAINTY_CONF.get(representative.rule_certainty, 0.65)
                    * representative.data_confidence,
                    3,
                )
                description = (
                    f"CPT {cpt_code} billed but no covered diagnosis found on the claim. "
                    f"LCD/NCD requires one of: {', '.join(required_icds[:5])}"
                    f"{'…' if len(required_icds) > 5 else ''}. "
                    f"Claim diagnoses present: {', '.join(sorted(all_icds)) or 'none'}. "
                    f"Source: {source}."
                )
            else:
                # Only supporting rules catalogued; absence is weaker evidence
                # (other valid DX may exist outside our catalogue).
                confidence = round(0.50 * representative.data_confidence, 3)
                supporting_icds = [r.icd_code for r in bucket["supporting"]]
                description = (
                    f"CPT {cpt_code} billed without any catalogued supporting diagnosis. "
                    f"Known covered DX include: {', '.join(supporting_icds[:5])}"
                    f"{'…' if len(supporting_icds) > 5 else ''}. "
                    f"No matching claim diagnosis found. Source: {source}."
                )

            results.append(DetectorResult(
                detector_code=self.code,
                finding_type="NO_COVERED_DX_FOR_CPT",
                description=description,
                overpayment_amount=overpayment,
                confidence_score=confidence,
                evidence={
                    "cpt_code": cpt_code,
                    "required_icds": [r.icd_code for r in bucket["required"]],
                    "supporting_icds": [r.icd_code for r in bucket["supporting"]],
                    "claim_icds": sorted(all_icds),
                    "has_required_rules": has_required,
                    "rule_certainty": representative.rule_certainty,
                    "data_confidence": representative.data_confidence,
                    "source_document": representative.source_document,
                    "source_authority": representative.source_authority,
                    "last_reviewed_at": representative.last_reviewed_at,
                    "affected_line_ids": [l.claim_line_id for l in affected_lines],
                    "overpayment": overpayment,
                },
            ))

        return results

    # ── Medical document helpers ─────────────────────────────────────────────

    async def _get_case_documents_text(self, claim: Claim, db_session: AsyncSession) -> Optional[str]:
        """Extract text from all attached documents to pass to the LLM evaluator.

        Returns concatenated document text, or None if no documents available.
        """
        from sqlalchemy import or_

        # Find the case associated with this claim
        case_result = await db_session.execute(
            select(OpaCase).where(OpaCase.claim_id == claim.claim_id)
        )
        case = case_result.scalar_one_or_none()

        # Query documents by case_id or claim_id
        doc_filter = []
        if case and case.case_id:
            doc_filter.append(Document.case_id == case.case_id)
        if claim.claim_id:
            doc_filter.append(Document.claim_id == claim.claim_id)

        if not doc_filter:
            return None

        result = await db_session.execute(
            select(Document).where(or_(*doc_filter))
        )
        documents = result.scalars().all()

        if not documents:
            return None

        # Concatenate extracted text from all documents
        texts = []
        for doc in documents:
            if doc.extracted_text:
                texts.append(f"[{doc.filename}]\n{doc.extracted_text}")

        return "\n\n".join(texts) if texts else None

    async def _search_clearlink_for_diagnoses(self, member_id: str) -> set[str]:
        """Query ClearLink for member's clinical diagnoses.

        Returns a set of diagnosis codes found in member's ClearLink medical records.
        This supplements attached documents with external clinical data.
        Safe to call even if ClearLink is not configured (returns empty set).
        """
        try:
            from .clearlink_detector_helper import search_clearlink_for_diagnoses
            return await search_clearlink_for_diagnoses(member_id)
        except ImportError:
            logger.debug("[DET-18] ClearLink detector helper not available")
            return set()
        except Exception as e:
            logger.warning(f"[DET-18] Error querying ClearLink for diagnoses: {e}")
            return set()

    async def _extract_diagnoses_from_case_documents(
        self, claim: Claim, db_session: AsyncSession
    ) -> set[str]:
        """Search documents attached to the case for diagnosis codes (ICD-10 format: [A-Z]\d{2}\.?\d*).

        Returns a set of diagnosis codes found in any attached medical notes, reports,
        or supporting documents. This allows DET-18 to recognize documented diagnoses
        that may not have been coded on the original claim submission.
        """
        found_icds: set[str] = set()

        # Query for documents linked to this claim OR to its case
        from sqlalchemy import or_

        # First, try to find the case associated with this claim
        case_result = await db_session.execute(
            select(OpaCase).where(OpaCase.claim_id == claim.claim_id)
        )
        case = case_result.scalar_one_or_none()

        # Query for documents linked to either the case or the claim.
        doc_filter = []
        if case and case.case_id:
            doc_filter.append(Document.case_id == case.case_id)
        if claim.claim_id:
            doc_filter.append(Document.claim_id == claim.claim_id)

        if not doc_filter:
            return found_icds

        result = await db_session.execute(
            select(Document).where(or_(*doc_filter))
        )
        documents = result.scalars().all()

        # Extract diagnosis codes from each document's extracted text.
        # ICD-10 format: letter followed by 2-3 digits, optional decimal + 1-2 digits
        # Examples: M17.11, E11.22, G43.909
        icd_pattern = re.compile(r'\b([A-Z]\d{2}(?:\.\d{1,2})?)\b')

        for doc in documents:
            if not doc.extracted_text:
                continue

            matches = icd_pattern.findall(doc.extracted_text)
            for icd in matches:
                # Normalize: remove trailing dot if present, uppercase
                icd_normalized = icd.rstrip('.').upper()
                found_icds.add(icd_normalized)
                logger.debug(f"[DET-18] Found diagnosis {icd_normalized} in document {doc.filename}")

        return found_icds

    # ── LLM helpers ──────────────────────────────────────────────────────────

    async def _ai_enabled(self, db_session: AsyncSession) -> bool:
        row = (await db_session.execute(
            select(RuntimeConfig).where(RuntimeConfig.key == "ai_suggestions_enabled")
        )).scalar_one_or_none()
        return row is not None and row.value.lower() in ("true", "1", "yes")

    async def _try_llm_evaluation(
        self,
        cpt_code: str,
        claim: Claim,
        affected_lines: list,
        all_icds: set,
        db_session: AsyncSession,
    ) -> Optional[DetectorResult]:
        """Run the DET-18 evaluation → verification two-step for an uncatalogued CPT.

        The evaluation makes two independent assessments:
          A) medical_necessity_met — is the procedure clinically warranted?
          B) coding_issue — do the ICD-10 codes satisfy the coverage requirement?

        Returns a DetectorResult only when the verifier confirms at least one issue.
        Returns None to fall back to the informational coverage-gap finding.
        """
        from ..services.ai_service import run_rule_prompt

        supporting = sorted(all_icds - {claim.primary_icd}) if claim.primary_icd else sorted(all_icds)

        # Get attached documents to pass to LLM
        medical_records = await self._get_case_documents_text(claim, db_session)
        logger.info(f"[DET-18] Medical records for CPT {cpt_code}: {bool(medical_records)} (len={len(medical_records) if medical_records else 0})")
        if medical_records:
            logger.debug(f"[DET-18] Medical records content (first 500 chars): {medical_records[:500]}")

        eval_vars: dict[str, str] = {
            "cpt_code": cpt_code,
            "primary_icd": claim.primary_icd or "none",
            "other_icd_codes": ", ".join(supporting) if supporting else "none",
            "pos_code": claim.pos_code or "N/A",
            "provider_specialty": claim.specialty or "Unknown",
            "medical_records": medical_records or "No attached medical records",
        }

        logger.info(f"[DET-18] Calling run_rule_prompt with medical_records variable present: {bool(medical_records)}")
        eval_out = await run_rule_prompt("DET-18", "evaluation", eval_vars)
        if eval_out is None:
            return None

        medical_necessity_met = bool(eval_out.get("medical_necessity_met", True))
        coding_issue = bool(eval_out.get("coding_issue", False))

        logger.info(f"[DET-18] LLM evaluation for CPT {cpt_code}: medical_necessity_met={medical_necessity_met}, coding_issue={coding_issue}")
        logger.info(f"[DET-18] LLM rationale: {eval_out.get('rationale', '')[:200]}")
        logger.info(f"[DET-18] LLM confidence: {eval_out.get('confidence')}")

        if medical_necessity_met and not coding_issue:
            logger.debug("[DET-18] CPT %s eval: necessity met, coding ok — no finding", cpt_code)
            return None

        eval_rationale = eval_out.get("rationale", "")
        covered_cited = eval_out.get("covered_indications_cited", "")
        coding_issue_description = eval_out.get("coding_issue_description", "")
        eval_confidence = float(eval_out.get("confidence", 0.5))

        issues: list[str] = []
        if not medical_necessity_met:
            issues.append("medical necessity not established")
        if coding_issue:
            issues.append(
                f"coding deficiency — {coding_issue_description}"
                if coding_issue_description
                else "ICD coding does not satisfy coverage requirement"
            )

        finding_description = (
            f"CPT {cpt_code}: {'; '.join(issues)}. "
            f"Diagnoses: {eval_vars['primary_icd']}"
            f"{', ' + eval_vars['other_icd_codes'] if supporting else ''}. "
            f"{eval_rationale}"
        )

        verify_vars: dict[str, str] = {
            "cpt_code": cpt_code,
            "primary_icd": eval_vars["primary_icd"],
            "other_icd_codes": eval_vars["other_icd_codes"],
            "pos_code": eval_vars["pos_code"],
            "lob": claim.lob or "Unknown",
            "medical_necessity_met": str(medical_necessity_met).lower(),
            "coding_issue": str(coding_issue).lower(),
            "coding_issue_description": coding_issue_description or "none",
            "finding_description": finding_description,
            "coverage_standard": eval_out.get("coverage_standard", "unknown"),
            "covered_indications_cited": covered_cited or "none identified",
            "initial_confidence": str(round(eval_confidence, 3)),
        }

        verify_out = await run_rule_prompt("DET-18", "verification", verify_vars)
        if verify_out is None:
            return None

        action = verify_out.get("recommended_action", "dismiss")
        if action == "dismiss":
            logger.debug("[DET-18] CPT %s verification: dismissed as false positive", cpt_code)
            return None

        necessity_confirmed = bool(verify_out.get("medical_necessity_confirmed", not medical_necessity_met))
        coding_confirmed = bool(verify_out.get("coding_issue_confirmed", coding_issue))
        confidence = round(float(verify_out.get("confidence", eval_confidence)), 3)
        overpayment = round(sum((l.paid_amount or 0.0) for l in affected_lines), 2)

        if necessity_confirmed and coding_confirmed:
            finding_type = "NO_COVERED_DX_FOR_CPT"
        elif necessity_confirmed:
            finding_type = "NO_MEDICAL_NECESSITY"
        else:
            finding_type = "CODING_DEFICIENCY_NO_COVERED_DX"

        confirmed_issues: list[str] = []
        if necessity_confirmed:
            confirmed_issues.append("medical necessity not established")
        if coding_confirmed:
            confirmed_issues.append(
                f"coding deficiency — {coding_issue_description}"
                if coding_issue_description
                else "ICD coding does not satisfy coverage requirement"
            )

        description = (
            f"CPT {cpt_code}: {'; '.join(confirmed_issues)}. "
            f"{eval_rationale} "
            f"Covered indications: {covered_cited}. "
            f"Claim diagnoses: {', '.join(sorted(all_icds)) or 'none'}."
        )
        if action == "request_medical_records":
            description += " Medical records requested to confirm coverage basis."

        return DetectorResult(
            detector_code=self.code,
            finding_type=finding_type,
            description=description,
            overpayment_amount=overpayment,
            confidence_score=confidence,
            evidence={
                "cpt_code": cpt_code,
                "claim_icds": sorted(all_icds),
                "llm_path": True,
                "medical_necessity_met": medical_necessity_met,
                "coding_issue": coding_issue,
                "coding_issue_description": coding_issue_description,
                "necessity_confirmed": necessity_confirmed,
                "coding_confirmed": coding_confirmed,
                "evaluation": eval_out,
                "verification": verify_out,
                "affected_line_ids": [l.claim_line_id for l in affected_lines],
                "overpayment": overpayment,
            },
        )
