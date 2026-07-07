"""Per-finding accept / reject / adjust endpoints (Phase 2)."""
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from ..middleware.auth import require_app
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user, assert_case_writable_by
from ..models.workflow import (
    Finding, FindingDisposition, OpaCase, AuditLog, OpaUser,
)


router = APIRouter(prefix="/api/findings", tags=["findings"], dependencies=[Depends(require_app("payguard"))])


class AcceptBody(BaseModel):
    reason: Optional[str] = None


class RejectBody(BaseModel):
    reason: str


class AdjustBody(BaseModel):
    adjusted_amount: float
    reason: str


class DispositionRead(BaseModel):
    finding_id: str
    status: str
    original_amount: float
    adjusted_amount: Optional[float] = None
    reason: Optional[str] = None
    decided_at: Optional[str] = None


async def _load_finding_and_case(db: AsyncSession, finding_id: str):
    f_res = await db.execute(select(Finding).where(Finding.finding_id == finding_id))
    finding = f_res.scalar_one_or_none()
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    # A claim can map to more than one case row; take the latest.
    case_res = await db.execute(
        select(OpaCase)
        .where(OpaCase.claim_id == finding.claim_id)
        .order_by(OpaCase.case_sequence.desc())
    )
    case = case_res.scalars().first()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found for finding")
    return finding, case


async def _load_disposition(db: AsyncSession, finding_id: str) -> FindingDisposition:
    res = await db.execute(
        select(FindingDisposition).where(FindingDisposition.finding_id == finding_id)
    )
    d = res.scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail="No disposition exists for this finding")
    return d


def _audit(case_id: str, user_id: str, action: str, reason: Optional[str]) -> AuditLog:
    return AuditLog(
        audit_id=str(uuid4()),
        case_id=case_id,
        actor_user_id=user_id,
        action=action,
        from_state=None,
        to_state=None,
        reason=(reason or "")[:500],
        meta_json="{}",
        created_at=datetime.utcnow().isoformat(),
    )


def _to_read(d: FindingDisposition) -> DispositionRead:
    return DispositionRead(
        finding_id=d.finding_id,
        status=d.status,
        original_amount=d.original_amount,
        adjusted_amount=d.adjusted_amount,
        reason=d.reason,
        decided_at=d.decided_at,
    )


@router.post("/{finding_id}/accept", response_model=DispositionRead)
async def accept_finding(
    finding_id: str,
    body: AcceptBody,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> DispositionRead:
    finding, case = await _load_finding_and_case(db, finding_id)
    assert_case_writable_by(case, current_user)
    d = await _load_disposition(db, finding_id)

    now = datetime.utcnow().isoformat()
    d.status = "accepted"
    d.adjusted_amount = None
    d.reason = body.reason
    d.decided_by_user_id = current_user.user_id
    d.decided_at = now

    db.add(_audit(
        case.case_id, current_user.user_id,
        f"FINDING_ACCEPTED:{finding.detector_id}", body.reason,
    ))
    from ..services.disposition_service import recompute_case_at_risk
    await recompute_case_at_risk(db, case.case_id)
    await db.commit()
    return _to_read(d)


@router.post("/{finding_id}/reject", response_model=DispositionRead)
async def reject_finding(
    finding_id: str,
    body: RejectBody,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> DispositionRead:
    if not body.reason or not body.reason.strip():
        raise HTTPException(status_code=400, detail="A reason is required to reject a finding")

    finding, case = await _load_finding_and_case(db, finding_id)
    assert_case_writable_by(case, current_user)
    d = await _load_disposition(db, finding_id)

    now = datetime.utcnow().isoformat()
    d.status = "rejected"
    d.adjusted_amount = None
    d.reason = body.reason.strip()
    d.decided_by_user_id = current_user.user_id
    d.decided_at = now

    db.add(_audit(
        case.case_id, current_user.user_id,
        f"FINDING_REJECTED:{finding.detector_id}", body.reason,
    ))
    from ..services.disposition_service import recompute_case_at_risk
    await recompute_case_at_risk(db, case.case_id)
    await db.commit()
    return _to_read(d)


@router.post("/{finding_id}/adjust", response_model=DispositionRead)
async def adjust_finding(
    finding_id: str,
    body: AdjustBody,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> DispositionRead:
    if not body.reason or not body.reason.strip():
        raise HTTPException(status_code=400, detail="A reason is required to adjust a finding")
    if body.adjusted_amount < 0:
        raise HTTPException(status_code=400, detail="Adjusted amount cannot be negative")

    finding, case = await _load_finding_and_case(db, finding_id)
    assert_case_writable_by(case, current_user)
    d = await _load_disposition(db, finding_id)

    now = datetime.utcnow().isoformat()
    d.status = "adjusted"
    d.adjusted_amount = float(body.adjusted_amount)
    d.reason = body.reason.strip()
    d.decided_by_user_id = current_user.user_id
    d.decided_at = now

    db.add(_audit(
        case.case_id, current_user.user_id,
        f"FINDING_ADJUSTED:{finding.detector_id}",
        f"${body.adjusted_amount:.2f} — {body.reason.strip()}",
    ))
    from ..services.disposition_service import recompute_case_at_risk
    await recompute_case_at_risk(db, case.case_id)
    await db.commit()
    return _to_read(d)
