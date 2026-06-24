from typing import List, Optional
from datetime import datetime
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from ..middleware.auth import require_app
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user, assert_case_writable_by
from ..services.siu_service import assert_not_siu_frozen
from ..models.workflow import OpaCase, OpaUser, CaseNote, AuditLog
from ..models.claims import Claim
from ..schemas.case_schemas import (
    CaseDetail,
    CaseCreate,
    CaseTransition,
    SupervisorDecision,
    CaseListResponse,
    WorklistFilters,
    AuditLogRead,
    RecoveryNoticeRead,
    CaseNoteRead,
    CaseNoteCreate,
    UserRead,
)
from ..schemas.guidance import CaseGuidance
from ..services.case_service import CaseService
from ..services.letter_service import LetterService
from ..services.detector_service import DetectorService
from ..services.recoupment_letter_service import (
    generate_recoupment_letter,
    RecoupmentLetterError,
)
from ..schemas.prepay_schemas import DocumentOut

router = APIRouter(prefix="/api/cases", tags=["cases"], dependencies=[Depends(require_app("payguard"))])


@router.get("", response_model=CaseListResponse)
async def list_cases(
    status: Optional[str] = Query(None),
    statuses: Optional[str] = Query(None, description="comma-separated statuses (OR) for queue views"),
    priority: Optional[str] = Query(None),
    lob: Optional[str] = Query(None),
    detector_code: Optional[str] = Query(None),
    assignee_id: Optional[str] = Query(None),
    scope: Optional[str] = Query(None, description="'mine_or_unassigned' restricts to current user + unassigned pool"),
    search: Optional[str] = Query(None),
    exclude_closed: bool = Query(False),
    closed_only: bool = Query(False),
    overdue_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> CaseListResponse:
    mine_filter = current_user.user_id if scope == "mine_or_unassigned" else None
    status_list = [s.strip() for s in statuses.split(",") if s.strip()] if statuses else None
    filters = WorklistFilters(
        status=status, statuses=status_list, priority=priority, lob=lob, detector_code=detector_code,
        assignee_id=assignee_id, search=search,
        mine_or_unassigned_for_user_id=mine_filter,
        exclude_closed=exclude_closed, closed_only=closed_only,
        overdue_only=overdue_only,
        # PayGuard is the post-pay app. Pre-pay (ClaimGuard) cases live on the
        # same DB but belong to ClaimGuard's UI — hard-filter them out here.
        pipeline_mode="post_pay",
    )
    skip = (page - 1) * page_size
    service = CaseService(db)
    return await service.get_worklist(filters, skip=skip, limit=page_size, page=page)


@router.get("/status-counts")
async def status_counts(
    scope: Optional[str] = Query(
        None, description="'mine_or_unassigned' restricts to current user + unassigned pool"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> dict:
    """Count of post-pay cases grouped by status — powers the left-nav stage
    badges. Org-wide by default; pass scope=mine_or_unassigned to scope to the
    caller's queue. Registered before /{case_id} so the literal path wins."""
    q = (
        select(OpaCase.status, func.count())
        .where(OpaCase.pipeline_mode == "post_pay")
        .group_by(OpaCase.status)
    )
    if scope == "mine_or_unassigned":
        q = q.where(
            or_(
                OpaCase.assigned_analyst_id == current_user.user_id,
                OpaCase.assigned_analyst_id.is_(None),
            )
        )
    rows = (await db.execute(q)).all()
    return {status: count for status, count in rows}


@router.get("/{case_id}", response_model=CaseDetail)
async def get_case(
    case_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> CaseDetail:
    service = CaseService(db)
    try:
        return await service.get_case_detail(case_id, user=current_user)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{case_id}/guidance", response_model=CaseGuidance)
async def get_case_guidance(
    case_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> CaseGuidance:
    """Workflow "where am I / what's next" guidance for a case, as seen by the
    caller (role/owner-aware). Used by the Assistant cockpit; the case page gets
    the same payload embedded in GET /{case_id}."""
    service = CaseService(db)
    try:
        detail = await service.get_case_detail(case_id, user=current_user)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return detail.guidance


@router.post("/{case_id}/recoupment-letter", response_model=DocumentOut, status_code=201)
async def create_recoupment_letter(
    case_id: int,
    current_user: OpaUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentOut:
    """Generate the provider recoupment letter PDF for this case and save it as
    a Document (kind='recoupment_letter'). Returns the saved document."""
    try:
        doc = await generate_recoupment_letter(
            db, case_sequence=case_id, user_id=current_user.user_id,
        )
    except RecoupmentLetterError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return DocumentOut(
        id=doc.document_id, claim_id=doc.claim_id, case_id=doc.case_id,
        filename=doc.filename, file_size_kb=doc.file_size_kb, kind=doc.kind,
        uploaded_at=doc.uploaded_at, uploaded_by_user_id=doc.uploaded_by_user_id,
    )


class BulkAssignRequest(BaseModel):
    case_ids: List[int]   # case_sequence values
    analyst_id: str


class BulkCloseRequest(BaseModel):
    case_ids: List[int]
    reason: Optional[str] = "Bulk written-off"


class BulkResult(BaseModel):
    success_ids: List[int]
    failures: List[dict]  # [{case_id, detail}]


@router.post("/bulk-assign", response_model=BulkResult)
async def bulk_assign(
    body: BulkAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> BulkResult:
    """Assign multiple cases to one analyst in one call. Supervisor/admin only."""
    if current_user.role not in ("supervisor", "admin"):
        raise HTTPException(status_code=403, detail="Supervisor role required for bulk assign")

    user_res = await db.execute(select(OpaUser).where(OpaUser.user_id == body.analyst_id))
    target = user_res.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Analyst not found")
    if target.role not in ("analyst", "supervisor", "admin"):
        raise HTTPException(status_code=400, detail="Target must be analyst/supervisor/admin")

    success: List[int] = []
    failures: List[dict] = []
    from ..services.notification_service import notify
    for seq in body.case_ids:
        case_res = await db.execute(select(OpaCase).where(OpaCase.case_sequence == seq))
        case = case_res.scalar_one_or_none()
        if case is None:
            failures.append({"case_id": seq, "detail": "not found"})
            continue
        if case.status == "pending_supervisor":
            failures.append({"case_id": seq, "detail": "locked: pending supervisor"})
            continue
        if case.siu_frozen:
            failures.append({"case_id": seq, "detail": "frozen by SIU investigation"})
            continue
        prev = case.assigned_analyst_id
        case.assigned_analyst_id = body.analyst_id
        if body.analyst_id and case.status == "new":
            case.status = "assigned"
        if body.analyst_id != prev and body.analyst_id != current_user.user_id:
            await notify(
                db,
                recipient_user_id=body.analyst_id,
                kind="case_assigned",
                title=f"Case {case.case_number} assigned to you",
                body=f"Assigned by {current_user.full_name} (bulk)",
                case_id=case.case_id,
                actor_user_id=current_user.user_id,
                link=f"/cases/{case.case_sequence}",
            )
        success.append(seq)

    await db.commit()
    return BulkResult(success_ids=success, failures=failures)


@router.post("/{case_sequence}/adjudicate-without-claim", response_model=CaseDetail)
async def adjudicate_without_claim(
    case_sequence: int,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> CaseDetail:
    """Override the 'awaiting 837' hold and adjudicate now, without the claim.

    Used when the 837 won't arrive (or isn't needed): clears the dx_pending gate
    and re-runs the FULL rule suite on the data on hand — note diagnoses are the
    835 placeholder, so the diagnosis-dependent rules reason over that. Analyst or
    supervisor. If the 837 later links, re-evaluation supersedes this.
    """
    if current_user.role not in ("analyst", "supervisor", "admin"):
        raise HTTPException(status_code=403, detail="Analyst or supervisor role required")
    case = (await db.execute(
        select(OpaCase).where(OpaCase.case_sequence == case_sequence)
    )).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.siu_frozen:
        raise HTTPException(status_code=400, detail="Case is frozen by an SIU investigation")
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == case.claim_id)
    )).scalar_one_or_none()
    if claim is None or not claim.dx_pending:
        raise HTTPException(status_code=400, detail="Case is not awaiting an 837")

    now = datetime.utcnow().isoformat()
    prior = case.status
    claim.dx_pending = False
    claim.updated_at = now
    if case.status == "awaiting_837":
        case.status = "new"
    case.updated_at = now
    db.add(AuditLog(
        audit_id=str(uuid4()),
        case_id=case.case_id,
        claim_id=case.claim_id,
        actor_user_id=current_user.user_id,
        action="Override: adjudicated without 837 — full rules run on available data",
        from_state=prior,
        to_state=case.status,
        reason="Analyst/supervisor override of awaiting-837 hold",
        meta_json="{}",
        created_at=now,
    ))
    await db.commit()

    from ..services.reevaluation_service import reevaluate_case
    await reevaluate_case(case_id=case.case_id, claim_id=case.claim_id)
    return await CaseService(db).get_case_detail(case_sequence, user=current_user)


@router.post("/bulk-close", response_model=BulkResult)
async def bulk_close(
    body: BulkCloseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> BulkResult:
    """Bulk-close cases as written-off. Per-case rules still apply (e.g. the
    $2K supervisor gate may route some cases to pending_supervisor instead)."""
    if current_user.role not in ("supervisor", "admin"):
        raise HTTPException(status_code=403, detail="Supervisor role required for bulk close")

    success: List[int] = []
    failures: List[dict] = []
    svc = CaseService(db)
    for seq in body.case_ids:
        # Skip frozen cases up front so the SIU hold isn't bypassed by bulk-close
        case_res = await db.execute(select(OpaCase).where(OpaCase.case_sequence == seq))
        c = case_res.scalar_one_or_none()
        if c and c.siu_frozen:
            failures.append({"case_id": seq, "detail": "frozen by SIU investigation"})
            continue
        try:
            await svc.transition(
                seq,
                CaseTransition(to_status="closed_written_off", reason=body.reason or "Bulk written-off"),
                acting_user_id=current_user.user_id,
            )
            success.append(seq)
        except ValueError as e:
            failures.append({"case_id": seq, "detail": str(e)})
    return BulkResult(success_ids=success, failures=failures)


class EscalateRequest(BaseModel):
    reason: str


class ResolveEscalationRequest(BaseModel):
    note: Optional[str] = None


@router.post("/{case_id}/escalate/resolve", status_code=201)
async def resolve_escalation(
    case_id: int,
    body: ResolveEscalationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> dict:
    """Supervisor (or admin) clears the escalation flag. Status of the case is
    untouched; this just writes an ESCALATION_RESOLVED audit entry so the
    serializer no longer reports an active escalation."""
    if current_user.role not in ("supervisor", "admin"):
        raise HTTPException(status_code=403, detail="Supervisor role required to resolve escalations")
    case = await _resolve_case_or_404(db, case_id)
    assert_not_siu_frozen(case)

    from datetime import datetime
    db.add(AuditLog(
        audit_id=str(uuid4()),
        case_id=case.case_id,
        actor_user_id=current_user.user_id,
        action="ESCALATION_RESOLVED",
        from_state=case.status,
        to_state=case.status,
        reason=(body.note or "").strip() or "Escalation resolved",
        meta_json="{}",
        created_at=datetime.utcnow().isoformat(),
    ))
    await db.commit()
    return {"status": "resolved"}


@router.post("/{case_id}/escalate", status_code=201)
async def escalate_to_supervisor(
    case_id: int,
    body: EscalateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> dict:
    """Flag a case for supervisor attention without changing its state.
    Notifies all active supervisors + writes an audit log entry."""
    if not body.reason or not body.reason.strip():
        raise HTTPException(status_code=400, detail="A reason is required to escalate")
    case = await _resolve_case_or_404(db, case_id)
    assert_case_writable_by(case, current_user)
    assert_not_siu_frozen(case)
    if case.status == "pending_supervisor":
        raise HTTPException(status_code=400, detail="Case is already awaiting supervisor")

    from datetime import datetime
    now = datetime.utcnow().isoformat()
    reason = body.reason.strip()

    db.add(AuditLog(
        audit_id=str(uuid4()),
        case_id=case.case_id,
        actor_user_id=current_user.user_id,
        action="ESCALATED_TO_SUPERVISOR",
        from_state=case.status,
        to_state=case.status,
        reason=reason,
        meta_json="{}",
        created_at=now,
    ))

    from ..services.notification_service import notify_supervisors
    count = await notify_supervisors(
        db,
        kind="escalation",
        title=f"Case escalated: {case.case_number}",
        body=f"{current_user.full_name} flagged for review: {reason[:140]}",
        case_id=case.case_id,
        actor_user_id=current_user.user_id,
        link=f"/cases/{case.case_sequence}",
    )

    await db.commit()
    return {"status": "escalated", "supervisors_notified": count}


@router.post("/{case_id}/transition", response_model=CaseDetail)
async def transition_case(
    case_id: int,
    body: CaseTransition,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> CaseDetail:
    case = await _resolve_case_or_404(db, case_id)
    assert_case_writable_by(case, current_user)
    assert_not_siu_frozen(case)
    service = CaseService(db)
    try:
        return await service.transition(case_id, body, acting_user_id=current_user.user_id)
    except ValueError as e:
        # Differentiate "not found" from validation errors
        msg = str(e)
        status = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=status, detail=msg)


@router.post("/{case_id}/approve", response_model=CaseDetail)
async def approve_case(
    case_id: int,
    body: SupervisorDecision,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> CaseDetail:
    if current_user.role not in ("supervisor", "admin"):
        raise HTTPException(status_code=403, detail="Supervisor role required")
    assert_not_siu_frozen(await _resolve_case_or_404(db, case_id))
    service = CaseService(db)
    try:
        return await service.approve_pending(
            case_id, supervisor_id=current_user.user_id, reason=body.reason,
        )
    except ValueError as e:
        msg = str(e)
        status = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=status, detail=msg)


@router.post("/{case_id}/reject", response_model=CaseDetail)
async def reject_case(
    case_id: int,
    body: SupervisorDecision,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> CaseDetail:
    if current_user.role not in ("supervisor", "admin"):
        raise HTTPException(status_code=403, detail="Supervisor role required")
    if not body.reason or not body.reason.strip():
        raise HTTPException(status_code=400, detail="A reason is required to reject")
    assert_not_siu_frozen(await _resolve_case_or_404(db, case_id))
    service = CaseService(db)
    try:
        return await service.reject_pending(
            case_id, supervisor_id=current_user.user_id, reason=body.reason,
        )
    except ValueError as e:
        msg = str(e)
        status = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=status, detail=msg)


@router.post("/{case_id}/reopen", response_model=CaseDetail)
async def reopen_case(
    case_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> CaseDetail:
    if current_user.role not in ("supervisor", "admin"):
        raise HTTPException(status_code=403, detail="Supervisor role required to reopen")
    assert_not_siu_frozen(await _resolve_case_or_404(db, case_id))
    reason = body.get("reason", "")
    service = CaseService(db)
    try:
        return await service.reopen(case_id, supervisor_id=current_user.user_id, reason=reason)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{case_id}/rerun-detectors")
async def rerun_detectors(
    case_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> dict:
    case = await _resolve_case_or_404(db, case_id)
    assert_case_writable_by(case, current_user)
    assert_not_siu_frozen(case)
    service = DetectorService(db)
    try:
        return await service.run_for_case(case_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class AssignRequest(BaseModel):
    analyst_id: Optional[str] = None  # None = unassign


class AtRiskOverrideRequest(BaseModel):
    amount: float
    reason: str


@router.patch("/{case_id}/override-amount", response_model=CaseDetail)
async def override_at_risk(
    case_id: int,
    body: AtRiskOverrideRequest,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> CaseDetail:
    """Supervisor manual override of total_overpayment_amount, with audit trail.
    Does NOT touch finding dispositions."""
    if current_user.role not in ("supervisor", "admin"):
        raise HTTPException(status_code=403, detail="Supervisor role required")
    if not body.reason or not body.reason.strip():
        raise HTTPException(status_code=400, detail="A reason is required")
    if body.amount < 0:
        raise HTTPException(status_code=400, detail="Amount cannot be negative")

    case = await _resolve_case_or_404(db, case_id)
    assert_not_siu_frozen(case)
    old_amount = case.total_overpayment_amount or 0.0
    case.total_overpayment_amount = body.amount
    await db.flush()

    db.add(AuditLog(
        audit_id=str(uuid4()),
        case_id=case.case_id,
        actor_user_id=current_user.user_id,
        action="AT_RISK_OVERRIDE",
        from_state=None,
        to_state=None,
        reason=f"${old_amount:.2f} → ${body.amount:.2f} — {body.reason.strip()}",
        meta_json="{}",
        created_at=datetime.utcnow().isoformat(),
    ))
    await db.commit()

    service = CaseService(db)
    return await service.get_case_detail(case_id, user=current_user)


@router.patch("/{case_id}/assign", response_model=CaseDetail)
async def assign_case(
    case_id: int,
    body: AssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> CaseDetail:
    case = await _resolve_case_or_404(db, case_id)
    assert_case_writable_by(case, current_user)
    assert_not_siu_frozen(case)

    # Authorization:
    #   - Self-assign (analyst taking ownership of an unassigned/own case) → allowed for analysts
    #   - Cross-assign or unassign someone else → supervisor/admin only
    is_self_assign = body.analyst_id == current_user.user_id
    if not is_self_assign and current_user.role not in ("supervisor", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Only supervisors can assign cases to other users",
        )

    if body.analyst_id is not None:
        user_res = await db.execute(select(OpaUser).where(OpaUser.user_id == body.analyst_id))
        user = user_res.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="Analyst not found")
        if user.role not in ("analyst", "supervisor", "admin"):
            raise HTTPException(status_code=400, detail="Target user must be an analyst, supervisor, or admin")

    previous_assignee = case.assigned_analyst_id
    case.assigned_analyst_id = body.analyst_id
    if body.analyst_id and case.status == "new":
        case.status = "assigned"

    await db.flush()

    # Notification: a *new* recipient gets pinged. Self-assigns and unassigns
    # don't generate a notification (no one to surprise).
    if body.analyst_id and body.analyst_id != current_user.user_id and body.analyst_id != previous_assignee:
        from ..services.notification_service import notify
        await notify(
            db,
            recipient_user_id=body.analyst_id,
            kind="case_assigned",
            title=f"Case {case.case_number} assigned to you",
            body=f"Assigned by {current_user.full_name}",
            case_id=case.case_id,
            actor_user_id=current_user.user_id,
            link=f"/cases/{case.case_sequence}",
        )
        await db.commit()

    service = CaseService(db)
    return await service.get_case_detail(case_id, user=current_user)


@router.get("/{case_id}/notices", response_model=List[RecoveryNoticeRead])
async def get_case_notices(
    case_id: int, db: AsyncSession = Depends(get_db)
) -> List[RecoveryNoticeRead]:
    service = LetterService(db)
    return await service.get_notices(case_id)


def _user_read(u: OpaUser) -> UserRead:
    return UserRead(
        id=u.user_id, username=u.username, full_name=u.full_name,
        email=u.email or "", role=u.role, is_active=u.is_active,
    )


async def _resolve_case_or_404(db: AsyncSession, case_id: int) -> OpaCase:
    res = await db.execute(select(OpaCase).where(OpaCase.case_sequence == case_id))
    case = res.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.get("/{case_id}/notes", response_model=List[CaseNoteRead])
async def list_case_notes(
    case_id: int, db: AsyncSession = Depends(get_db)
) -> List[CaseNoteRead]:
    case = await _resolve_case_or_404(db, case_id)
    res = await db.execute(
        select(CaseNote).where(CaseNote.case_id == case.case_id)
        .order_by(CaseNote.created_at)
    )
    notes = res.scalars().all()
    return [
        CaseNoteRead(
            id=n.note_id, body=n.body, created_at=n.created_at,
            author=_user_read(n.author) if n.author else None,
        )
        for n in notes
    ]


_MENTION_RE = __import__("re").compile(r"@([a-z][a-z0-9._-]{1,30})", __import__("re").IGNORECASE)


@router.post("/{case_id}/notes", response_model=CaseNoteRead, status_code=201)
async def add_case_note(
    case_id: int,
    body: CaseNoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> CaseNoteRead:
    if not body.body or not body.body.strip():
        raise HTTPException(status_code=400, detail="Note body cannot be empty")

    case = await _resolve_case_or_404(db, case_id)
    now = datetime.utcnow().isoformat()
    note_body = body.body.strip()
    note = CaseNote(
        note_id=str(uuid4()),
        case_id=case.case_id,
        author_user_id=current_user.user_id,
        body=note_body,
        created_at=now,
    )
    db.add(note)

    db.add(AuditLog(
        audit_id=str(uuid4()),
        case_id=case.case_id,
        actor_user_id=current_user.user_id,
        action="note_added",
        from_state=case.status,
        to_state=case.status,
        reason=note_body[:200],
        meta_json="{}",
        created_at=now,
    ))

    # @mentions: notify any users named with @username in the note body
    mentioned_usernames = {m.lower() for m in _MENTION_RE.findall(note_body)}
    mentioned_usernames.discard(current_user.username.lower())  # don't self-notify
    if mentioned_usernames:
        from sqlalchemy import func as sa_func
        users_res = await db.execute(
            select(OpaUser).where(sa_func.lower(OpaUser.username).in_(mentioned_usernames))
        )
        from ..services.notification_service import notify
        snippet = note_body[:140] + ('…' if len(note_body) > 140 else '')
        for u in users_res.scalars().all():
            if u.user_id == current_user.user_id:
                continue
            await notify(
                db,
                recipient_user_id=u.user_id,
                kind="note_mention",
                title=f"{current_user.full_name} mentioned you on {case.case_number}",
                body=snippet,
                case_id=case.case_id,
                actor_user_id=current_user.user_id,
                link=f"/cases/{case.case_sequence}",
            )

    await db.commit()
    return CaseNoteRead(
        id=note.note_id, body=note.body, created_at=note.created_at,
        author=_user_read(current_user),
    )
