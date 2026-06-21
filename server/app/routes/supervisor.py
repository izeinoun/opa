"""Supervisor-only listing endpoints (Phase 3).

- GET /api/supervisor/approvals — every case in pending_supervisor with
  the stashed decision_metadata inlined.
- GET /api/supervisor/assignments — workload buckets by analyst + the
  unassigned-case pool.
"""
from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from ..middleware.auth import require_role
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.workflow import OpaCase, OpaUser
from ..models.claims import Claim


router = APIRouter(prefix="/api/supervisor", tags=["supervisor"], dependencies=[Depends(require_role("supervisor", "admin"))])

# PayGuard supervisor queues. Pre-pay cases live on the same DB but flow
# through ClaimGuard's reviewer surface, so filter them out here.
_POST_PAY = Claim.pipeline_mode == "post_pay"


def _require_supervisor(user: OpaUser) -> None:
    if user.role not in ("supervisor", "admin"):
        raise HTTPException(status_code=403, detail="Supervisor role required")


class PendingApproval(BaseModel):
    case_id: str
    case_sequence: int
    case_number: str
    lob: str
    at_risk_amount: float
    submitted_by: Optional[str] = None
    submitted_by_full_name: Optional[str] = None
    submitted_at: Optional[str] = None
    disposition: Optional[str] = None
    reason: Optional[str] = None
    recovered_amount: Optional[float] = None
    case_assignee_full_name: Optional[str] = None


@router.get("/approvals", response_model=List[PendingApproval])
async def list_pending_approvals(
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> List[PendingApproval]:
    _require_supervisor(current_user)
    res = await db.execute(
        select(OpaCase)
        .join(Claim, OpaCase.claim_id == Claim.claim_id)
        .where(OpaCase.status == "pending_supervisor", _POST_PAY)
        .order_by(OpaCase.updated_at.desc())
    )
    cases = list(res.scalars().all())

    # Bulk-load referenced users
    user_ids = set()
    for c in cases:
        if c.assigned_analyst_id:
            user_ids.add(c.assigned_analyst_id)
        if c.decision_metadata:
            try:
                meta = json.loads(c.decision_metadata)
                uid = meta.get("submitted_by_user_id")
                if uid:
                    user_ids.add(uid)
            except Exception:
                pass
    user_lookup: dict = {}
    if user_ids:
        ures = await db.execute(select(OpaUser).where(OpaUser.user_id.in_(user_ids)))
        user_lookup = {u.user_id: u for u in ures.scalars().all()}

    out: List[PendingApproval] = []
    for c in cases:
        meta = {}
        if c.decision_metadata:
            try:
                meta = json.loads(c.decision_metadata)
            except Exception:
                meta = {}
        submitter = user_lookup.get(meta.get("submitted_by_user_id")) if meta else None
        assignee = user_lookup.get(c.assigned_analyst_id) if c.assigned_analyst_id else None
        out.append(PendingApproval(
            case_id=c.case_id,
            case_sequence=c.case_sequence,
            case_number=c.case_number,
            lob=c.lob,
            at_risk_amount=c.total_overpayment_amount,
            submitted_by=meta.get("submitted_by_user_id"),
            submitted_by_full_name=submitter.full_name if submitter else None,
            submitted_at=meta.get("submitted_at"),
            disposition=meta.get("disposition"),
            reason=meta.get("reason"),
            recovered_amount=meta.get("recovered_amount"),
            case_assignee_full_name=assignee.full_name if assignee else None,
        ))
    return out


class AnalystWorkload(BaseModel):
    user_id: str
    full_name: str
    username: str
    role: str
    total_active: int
    new: int = 0
    assigned: int = 0
    in_review: int = 0
    ready_for_notice: int = 0
    pending_supervisor: int = 0
    notice_sent: int = 0
    provider_responded: int = 0
    reconciling: int = 0


class UnassignedCase(BaseModel):
    case_id: str
    case_sequence: int
    case_number: str
    status: str
    priority: str
    priority_score: float
    at_risk_amount: float
    lob: str
    primary_detector_id: str
    deadline_date: Optional[str] = None


class AssignmentsResponse(BaseModel):
    analysts: List[AnalystWorkload]
    unassigned: List[UnassignedCase]


_ACTIVE_STATUSES = {
    "awaiting_837",
    "new", "assigned", "in_review", "ready_for_notice",
    "pending_supervisor", "notice_sent", "provider_responded", "reconciling",
}


@router.get("/assignments", response_model=AssignmentsResponse)
async def list_assignments(
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> AssignmentsResponse:
    _require_supervisor(current_user)

    # Pull active post-pay cases (is_active = true). Group by analyst.
    cases_res = await db.execute(
        select(OpaCase)
        .join(Claim, OpaCase.claim_id == Claim.claim_id)
        .where(OpaCase.is_active == True, _POST_PAY)  # noqa: E712
    )
    cases = list(cases_res.scalars().all())

    # Load all analyst-ish users (analysts and supervisors) so even zero-load users appear.
    users_res = await db.execute(
        select(OpaUser).where(OpaUser.role.in_(("analyst", "supervisor"))).where(OpaUser.is_active == True)  # noqa: E712
    )
    users = list(users_res.scalars().all())
    by_user: dict = {u.user_id: AnalystWorkload(
        user_id=u.user_id, full_name=u.full_name, username=u.username, role=u.role,
        total_active=0,
    ) for u in users}

    unassigned: List[UnassignedCase] = []
    for c in cases:
        if c.assigned_analyst_id and c.assigned_analyst_id in by_user:
            w = by_user[c.assigned_analyst_id]
            if c.status in _ACTIVE_STATUSES:
                w.total_active += 1
                key = c.status
                if hasattr(w, key):
                    setattr(w, key, getattr(w, key) + 1)
        elif not c.assigned_analyst_id and c.status in _ACTIVE_STATUSES:
            unassigned.append(UnassignedCase(
                case_id=c.case_id,
                case_sequence=c.case_sequence,
                case_number=c.case_number,
                status=c.status,
                priority=c.priority,
                priority_score=c.priority_score,
                at_risk_amount=c.total_overpayment_amount,
                lob=c.lob,
                primary_detector_id=c.primary_detector_id,
                deadline_date=c.deadline_date,
            ))

    analysts_sorted = sorted(by_user.values(), key=lambda w: (-w.total_active, w.full_name))
    unassigned.sort(key=lambda c: -c.priority_score)
    return AssignmentsResponse(analysts=analysts_sorted, unassigned=unassigned)


class ActiveEscalation(BaseModel):
    case_id: str
    case_sequence: int
    case_number: str
    case_status: str
    case_priority: str
    lob: str
    at_risk_amount: float
    case_assignee_full_name: Optional[str] = None
    escalated_by_full_name: Optional[str] = None
    escalated_at: str
    reason: Optional[str] = None


@router.get("/escalations", response_model=List[ActiveEscalation])
async def list_active_escalations(
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> List[ActiveEscalation]:
    """Active escalations: cases where the most recent escalate-related audit
    log entry is ESCALATED_TO_SUPERVISOR (not yet ESCALATION_RESOLVED)."""
    _require_supervisor(current_user)
    from ..models.workflow import AuditLog

    # Pull all escalation-related events for active cases, newest first
    res = await db.execute(
        select(AuditLog, OpaCase)
        .join(OpaCase, OpaCase.case_id == AuditLog.case_id)
        .join(Claim, OpaCase.claim_id == Claim.claim_id)
        .where(AuditLog.action.in_(("ESCALATED_TO_SUPERVISOR", "ESCALATION_RESOLVED")), _POST_PAY)
        .order_by(AuditLog.created_at.desc())
    )
    rows = list(res.all())

    # Walk cases newest-event-first; first event per case decides "active or resolved"
    seen_cases: set = set()
    active: list = []
    for log, case in rows:
        if case.case_id in seen_cases:
            continue
        seen_cases.add(case.case_id)
        if log.action == "ESCALATED_TO_SUPERVISOR":
            actor_name = log.actor.full_name if log.actor else None
            assignee_name = case.assigned_analyst.full_name if case.assigned_analyst else None
            active.append(ActiveEscalation(
                case_id=case.case_id,
                case_sequence=case.case_sequence,
                case_number=case.case_number,
                case_status=case.status,
                case_priority=case.priority,
                lob=case.lob,
                at_risk_amount=case.total_overpayment_amount or 0.0,
                case_assignee_full_name=assignee_name,
                escalated_by_full_name=actor_name,
                escalated_at=log.created_at,
                reason=log.reason,
            ))

    # Sort newest first
    active.sort(key=lambda e: e.escalated_at, reverse=True)
    return active
