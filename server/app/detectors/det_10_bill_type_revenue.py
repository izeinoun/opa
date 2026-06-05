from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..dao.bill_revenue_dao import BillRevenueDAO
from ..models.claims import Claim

_INSTITUTIONAL_FORM_TYPES = {"UB-04", "ub-04", "ub04"}
_INSTITUTIONAL_CARE_SETTINGS = {"Inpatient", "inpatient"}


def _is_institutional(claim: Claim) -> bool:
    if claim.claim_form_type and claim.claim_form_type in _INSTITUTIONAL_FORM_TYPES:
        return True
    if claim.care_setting and claim.care_setting in _INSTITUTIONAL_CARE_SETTINGS:
        return True
    return False


class BillTypeRevenueDetector(BaseDetector):
    code = "DET-10"
    name = "Bill Type / Revenue Code Validity"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        if not _is_institutional(claim):
            return []

        dao = BillRevenueDAO(db_session)
        findings: List[DetectorResult] = []

        # ── Bill type ─────────────────────────────────────────────────────────
        bill_type = (claim.bill_type or "").strip()
        if not bill_type:
            findings.append(DetectorResult(
                detector_code=self.code,
                finding_type="MISSING_BILL_TYPE",
                description=(
                    "Institutional claim (UB-04) is missing the bill type code. "
                    "A valid bill type is required for facility-type and frequency identification."
                ),
                overpayment_amount=0.0,
                confidence_score=0.92,
                evidence={
                    "bill_type": None,
                    "claim_form_type": claim.claim_form_type,
                    "care_setting": claim.care_setting,
                },
            ))
        else:
            valid = await dao.bill_type_exists(bill_type)
            if not valid:
                findings.append(DetectorResult(
                    detector_code=self.code,
                    finding_type="INVALID_BILL_TYPE",
                    description=(
                        f"Bill type '{bill_type}' is not present in the bill type reference table. "
                        "Unrecognized facility type or frequency code."
                    ),
                    overpayment_amount=0.0,
                    confidence_score=0.88,
                    evidence={
                        "bill_type": bill_type,
                        "claim_form_type": claim.claim_form_type,
                        "care_setting": claim.care_setting,
                    },
                ))

        # ── Revenue codes ─────────────────────────────────────────────────────
        invalid_lines = []
        missing_lines = []
        for line in (claim.lines or []):
            rc = (line.revenue_code or "").strip()
            if not rc:
                missing_lines.append({
                    "line_number": line.line_number,
                    "cpt_code": line.cpt_code,
                })
            else:
                valid = await dao.revenue_code_exists(rc)
                if not valid:
                    invalid_lines.append({
                        "line_number": line.line_number,
                        "revenue_code": rc,
                        "cpt_code": line.cpt_code,
                    })

        if missing_lines or invalid_lines:
            all_bad = missing_lines + invalid_lines
            findings.append(DetectorResult(
                detector_code=self.code,
                finding_type="INVALID_REVENUE_CODE",
                description=(
                    f"{len(all_bad)} service line(s) have a missing or unrecognized revenue code. "
                    "Revenue codes are required on all UB-04 lines."
                ),
                overpayment_amount=0.0,
                confidence_score=0.88,
                evidence={
                    "missing_revenue_code_lines": missing_lines,
                    "invalid_revenue_code_lines": invalid_lines,
                    "total_bad_lines": len(all_bad),
                },
            ))

        return findings
