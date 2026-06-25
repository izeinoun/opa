"""Re-evaluate rules for a case — useful when diagnosis codes change or rules are updated."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import require_role
from ..models.workflow import OpaCase, OpaUser
from ..schemas.case_schemas import CaseDetail
from ..services.detector_service import DetectorService
from ..services.case_service import get_case_detail

router = APIRouter(prefix="/api/cases", tags=["rules"], dependencies=[Depends(require_role("analyst", "admin"))])


class ReevaluateRulesRequest(BaseModel):
    case_id: str


class ReevaluateRulesResponse(BaseModel):
    case_id: str
    case_number: str
    previous_finding_count: int
    new_finding_count: int
    new_findings: list
    updated_likelihood: float
    updated_priority: float
    message: str


@router.post("/{case_id}/reevaluate-rules", response_model=ReevaluateRulesResponse)
async def reevaluate_case_rules(
    case_id: str,
    user: OpaUser = Depends(require_role("analyst", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Re-run all detectors on a case from scratch.

    Useful when:
    - Diagnosis codes change (837 enrichment updates primary_icd)
    - Rules are updated
    - Analyst wants to verify current state

    This will:
    1. Delete all existing findings
    2. Re-run detectors against the current claim
    3. Recalculate likelihood and priority
    4. Log the re-evaluation in audit trail
    """

    # Get case
    case_res = await db.execute(
        select(OpaCase).where(OpaCase.case_id == case_id)
    )
    case = case_res.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    # Get previous findings count for comparison
    from sqlalchemy import func
    from ..models.workflow import CaseFinding

    old_findings_res = await db.execute(
        select(func.count(CaseFinding.finding_id)).where(
            CaseFinding.case_id == case_id
        )
    )
    old_count = old_findings_res.scalar() or 0

    # Run detector service
    try:
        detector_service = DetectorService(db)
        await detector_service.run_for_case(case.case_sequence)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to re-evaluate rules: {str(e)}"
        )

    # Get updated case detail
    try:
        case_detail = await get_case_detail(db, case_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve updated case: {str(e)}"
        )

    if not case_detail:
        raise HTTPException(status_code=404, detail="Case detail not found after evaluation")

    # Log the re-evaluation
    from ..dao.audit_log_dao import AuditLogDAO
    audit_dao = AuditLogDAO(db)

    new_count = len(case_detail.findings or [])
    action = f"Re-evaluated rules; {old_count} findings → {new_count} findings"
    await audit_dao.log(
        actor_user_id=user.user_id,
        action=action,
        case_id=case_id,
    )
    await db.commit()

    # Format findings for response
    findings_response = []
    if case_detail.findings:
        for f in case_detail.findings:
            findings_response.append({
                "detector_id": f.detector_id,
                "title": f.title or f.description or f.detector_id,
                "overpayment_amount": f.overpayment_amount,
                "confidence": f.confidence_score,
            })

    return ReevaluateRulesResponse(
        case_id=case_id,
        case_number=case.case_number,
        previous_finding_count=old_count,
        new_finding_count=new_count,
        new_findings=findings_response,
        updated_likelihood=case_detail.likelihood_score,
        updated_priority=case_detail.priority_score,
        message=f"Rules re-evaluated: {new_count} finding(s) identified" + (
            f" (was {old_count})" if old_count != new_count else ""
        ),
    )
