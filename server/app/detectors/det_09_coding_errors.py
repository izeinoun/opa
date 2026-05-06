from typing import List, Set, Tuple
import json
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim

INVALID_DX_CPT_COMBOS: Set[Tuple[str, str]] = {
    # Original clinical rules
    ("E11.9",  "99385"),   # Diabetes + preventive well visit
    ("Z00.00", "27447"),   # Well visit + total knee arthroplasty
    ("J06.9",  "93306"),   # Upper respiratory infection + echocardiogram
    ("M79.3",  "70553"),   # Panniculitis + brain MRI
    ("F41.1",  "36415"),   # Anxiety + venipuncture
    # Mismatches identified in claim analysis
    ("M17.11", "93458"),   # Knee OA + left heart cath (no cardiac indication)
    ("M54.5",  "93458"),   # Low back pain + left heart cath
    ("M17.12", "93306"),   # Knee OA + echocardiogram
    ("G43.909","27447"),   # Migraine + total knee arthroplasty
    ("I25.10", "97110"),   # Stable CAD + therapeutic exercise (unbundled)
    ("I25.10", "72148"),   # Stable CAD + lumbar MRI
}

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

        claim_cpt_codes = {line.cpt_code for line in lines}

        all_icd_codes: Set[str] = set()
        for line in lines:
            try:
                icd_list = json.loads(line.icd_codes) if isinstance(line.icd_codes, str) else []
                all_icd_codes.update(icd_list)
            except (json.JSONDecodeError, TypeError):
                pass

        for (icd_code, cpt_code) in INVALID_DX_CPT_COMBOS:
            if icd_code in all_icd_codes and cpt_code in claim_cpt_codes:
                affected_lines = [l for l in lines if l.cpt_code == cpt_code]
                overpayment = sum(l.paid_amount for l in affected_lines)
                results.append(DetectorResult(
                    detector_code=self.code,
                    finding_type="DX_CPT_MISMATCH",
                    description=(
                        f"Invalid ICD-CPT combination: diagnosis {icd_code} does not "
                        f"support procedure {cpt_code}."
                    ),
                    overpayment_amount=round(overpayment, 2),
                    confidence_score=0.75,
                    evidence={
                        "icd_code": icd_code,
                        "cpt_code": cpt_code,
                        "affected_line_ids": [l.claim_line_id for l in affected_lines],
                        "overpayment": round(overpayment, 2),
                    },
                ))

        for global_code, component_codes in BUNDLED_CODES.items():
            if global_code in claim_cpt_codes:
                unbundled = [c for c in component_codes if c in claim_cpt_codes]
                if unbundled:
                    affected_lines = [l for l in lines if l.cpt_code in unbundled]
                    overpayment = sum(l.paid_amount for l in affected_lines)
                    results.append(DetectorResult(
                        detector_code=self.code,
                        finding_type="UNBUNDLING",
                        description=(
                            f"Unbundling detected: {global_code} billed alongside component "
                            f"code(s) {unbundled} that should be bundled."
                        ),
                        overpayment_amount=round(overpayment, 2),
                        confidence_score=0.75,
                        evidence={
                            "global_code": global_code,
                            "unbundled_codes": unbundled,
                            "affected_line_ids": [l.claim_line_id for l in affected_lines],
                            "overpayment": round(overpayment, 2),
                        },
                    ))

        return results
