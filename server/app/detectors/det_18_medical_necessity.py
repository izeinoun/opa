import json
from collections import defaultdict
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim
from ..models.reference import CptDxCoverage

_CERTAINTY_CONF = {"mandatory": 0.80, "guideline": 0.65, "heuristic": 0.50}


class MedicalNecessityDetector(BaseDetector):
    code = "DET-18"
    name = "Medical Necessity Detector"
    # Medical necessity denials are coverage/clinical determinations, not FWA.
    fwa_rule_code = None

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
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
            try:
                icd_list = json.loads(line.icd_codes) if isinstance(line.icd_codes, str) else []
                all_icds.update(c for c in icd_list if c)
            except (json.JSONDecodeError, TypeError):
                pass

        # Pull all required/supporting coverage rules for CPTs on the claim.
        res = await db_session.execute(
            select(CptDxCoverage).where(
                CptDxCoverage.cpt_code.in_(claim_cpts),
                CptDxCoverage.coverage_type.in_(["required", "supporting"]),
            )
        )
        coverage_rows = res.scalars().all()
        if not coverage_rows:
            return results  # no catalogue entries — nothing to judge

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
