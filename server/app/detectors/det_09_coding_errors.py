import json
from typing import List, Set
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim
from ..models.reference import CptDxCoverage

# Bundling rules stay hardcoded — comprehensive→component relationships are
# defined by NCCI policy and don't map naturally to the CPT-DX coverage table.
BUNDLED_CODES = {
    "27447": ["27310", "27370", "27372"],
    "43239": ["43235", "43236"],
    "93306": ["93307", "93308"],
    "99215": ["99212", "99213", "99214"],
    "70553": ["70551", "70552"],
}


class CodingErrorDetector(BaseDetector):
    code = "DET-09"
    name = "Coding/Documentation Error Detector"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        results = []
        lines = claim.lines or []
        if not lines:
            return results

        # UB-04 inpatient facility claims are DRG-billed; CPT/HCPCS codes must
        # not appear on service lines (inpatient procedures belong in ICD-10-PCS).
        # Flag any CPT lines present and skip the rest of the CPT-based checks.
        if (getattr(claim, "claim_form_type", None) == "UB-04"
                and getattr(claim, "care_setting", None) == "Inpatient"):
            cpt_lines = [l for l in lines if l.cpt_code]
            if cpt_lines:
                codes = ", ".join(sorted({l.cpt_code for l in cpt_lines}))
                results.append(DetectorResult(
                    detector_code=self.code,
                    finding_type="CPT_ON_INPATIENT_UB04",
                    description=(
                        f"CPT/HCPCS code(s) {codes} billed on a UB-04 inpatient "
                        f"(institutional) claim. Inpatient facility claims are "
                        f"DRG-based; procedures must be coded in ICD-10-PCS, not CPT. "
                        f"CMS-1450 FL 44 should carry revenue codes, not CPT."
                    ),
                    overpayment_amount=round(
                        sum(l.paid_amount or 0.0 for l in cpt_lines), 2
                    ),
                    confidence_score=0.95,
                    evidence={
                        "cpt_codes": sorted({l.cpt_code for l in cpt_lines}),
                        "affected_line_ids": [l.claim_line_id for l in cpt_lines],
                    },
                ))
            return results

        claim_cpts: Set[str] = {line.cpt_code for line in lines}

        all_icd_codes: Set[str] = set()
        if claim.primary_icd and claim.primary_icd.strip():
            all_icd_codes.add(claim.primary_icd.strip())
        for line in lines:
            try:
                icd_list = json.loads(line.icd_codes) if isinstance(line.icd_codes, str) else []
                all_icd_codes.update(c for c in icd_list if c)
            except (json.JSONDecodeError, TypeError):
                pass

        # ── DX-CPT mismatch: query cpt_dx_coverage ────────────────────────
        # An 'excluded' pair means this ICD code indicates the CPT is not
        # medically necessary. Confidence is scaled by the row's data_confidence
        # and rule_certainty so the finding reflects the reference data's own
        # stated confidence.
        if claim_cpts and all_icd_codes:
            res = await db_session.execute(
                select(CptDxCoverage).where(
                    CptDxCoverage.cpt_code.in_(claim_cpts),
                    CptDxCoverage.icd_code.in_(all_icd_codes),
                    CptDxCoverage.coverage_type == "excluded",
                )
            )
            excluded_pairs = res.scalars().all()

            for pair in excluded_pairs:
                _CERTAINTY_SCORE = {"mandatory": 0.90, "guideline": 0.70, "heuristic": 0.55}
                base_confidence = _CERTAINTY_SCORE.get(pair.rule_certainty, 0.70)
                confidence = round(base_confidence * pair.data_confidence, 3)

                affected_lines = [l for l in lines if l.cpt_code == pair.cpt_code]
                overpayment = sum(
                    (l.paid_amount or 0.0) for l in affected_lines
                )

                source = f"{pair.source_document} ({pair.source_authority})" if pair.source_document else "Clinical guidelines"
                results.append(DetectorResult(
                    detector_code=self.code,
                    finding_type="DX_CPT_MISMATCH",
                    description=(
                        f"Diagnosis {pair.icd_code} does not support procedure {pair.cpt_code}. "
                        f"{pair.rationale or ''} Source: {source}."
                    ),
                    overpayment_amount=round(overpayment, 2),
                    confidence_score=confidence,
                    evidence={
                        "cpt_code": pair.cpt_code,
                        "icd_code": pair.icd_code,
                        "coverage_type": pair.coverage_type,
                        "rule_certainty": pair.rule_certainty,
                        "data_confidence": pair.data_confidence,
                        "source_document": pair.source_document,
                        "source_authority": pair.source_authority,
                        "last_reviewed_at": pair.last_reviewed_at,
                        "affected_line_ids": [l.claim_line_id for l in affected_lines],
                        "overpayment": round(overpayment, 2),
                    },
                ))

        # ── Unbundling: component codes billed alongside comprehensive ────
        for global_code, component_codes in BUNDLED_CODES.items():
            if global_code in claim_cpts:
                unbundled = [c for c in component_codes if c in claim_cpts]
                if unbundled:
                    affected_lines = [l for l in lines if l.cpt_code in unbundled]
                    overpayment = sum((l.paid_amount or 0.0) for l in affected_lines)
                    results.append(DetectorResult(
                        detector_code=self.code,
                        finding_type="UNBUNDLING",
                        description=(
                            f"Unbundling detected: {global_code} billed alongside component "
                            f"code(s) {unbundled} that are included in the comprehensive code."
                        ),
                        overpayment_amount=round(overpayment, 2),
                        confidence_score=0.80,
                        evidence={
                            "global_code": global_code,
                            "unbundled_codes": unbundled,
                            "affected_line_ids": [l.claim_line_id for l in affected_lines],
                            "overpayment": round(overpayment, 2),
                        },
                    ))

        return results
