"""Recovery / recoupment entry endpoints (Phase 4)."""
from datetime import datetime
from typing import List, Optional
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from ..middleware.auth import require_app
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user, assert_case_writable_by
from ..models.workflow import OpaCase, RecoupmentAction, AuditLog, OpaUser


router = APIRouter(prefix="/api/cases", tags=["recoupments"], dependencies=[Depends(require_app("payguard"))])


_VALID_METHODS = {"check", "eft", "adjustment", "credit_balance", "other"}
_ALLOWED_FROM = {"notice_sent", "provider_responded", "reconciling"}


class RecoupmentCreate(BaseModel):
    amount: float = Field(gt=0)
    method: str
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class RecoupmentRead(BaseModel):
    id: str
    amount: float
    method: str
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    recorded_by_full_name: Optional[str] = None
    recorded_at: str


def _to_read(r: RecoupmentAction, recorder_name: Optional[str]) -> RecoupmentRead:
    meta = {}
    if r.staging_output_json:
        try:
            meta = json.loads(r.staging_output_json)
        except Exception:
            meta = {}
    return RecoupmentRead(
        id=r.recoupment_id,
        amount=r.requested_amount,
        method=r.method,
        reference_number=meta.get("reference_number"),
        notes=meta.get("notes"),
        recorded_by_full_name=recorder_name,
        recorded_at=r.confirmed_at or r.submitted_at or r.created_at,
    )


@router.post("/{case_id}/recoupments", response_model=RecoupmentRead, status_code=201)
async def record_recoupment(
    case_id: int,
    body: RecoupmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> RecoupmentRead:
    if body.method not in _VALID_METHODS:
        raise HTTPException(
            status_code=400,
            detail=f"method must be one of {sorted(_VALID_METHODS)}",
        )

    case_res = await db.execute(select(OpaCase).where(OpaCase.case_sequence == case_id))
    case = case_res.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    assert_case_writable_by(case, current_user)

    if case.status not in _ALLOWED_FROM:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot record recovery while case is in '{case.status}'. "
                   f"Case must be in one of: {sorted(_ALLOWED_FROM)}",
        )

    now = datetime.utcnow().isoformat()
    rec = RecoupmentAction(
        recoupment_id=str(uuid4()),
        case_id=case.case_id,
        method=body.method,
        requested_amount=body.amount,
        status="confirmed",
        submitted_at=now,
        confirmed_at=now,
        recovery_835_transaction_id=None,
        staging_output_json=json.dumps({
            "reference_number": body.reference_number,
            "notes": body.notes,
            "recorded_by_user_id": current_user.user_id,
        }),
        staging_status="manual_entry",
        staging_exported_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(rec)
    await db.flush()  # so the reconciliation sum below includes this recovery

    # Reconciliation: once recorded recoveries cover the overpayment, the case is
    # recouped AND reconciled → close it as recovered (done). Otherwise it stays
    # in reconciling, awaiting the remainder.
    from_state = case.status
    overpayment = case.total_overpayment_amount or 0.0
    recovered = (await db.execute(
        select(func.coalesce(func.sum(RecoupmentAction.requested_amount), 0.0))
        .where(
            RecoupmentAction.case_id == case.case_id,
            RecoupmentAction.status == "confirmed",
        )
    )).scalar() or 0.0
    if overpayment > 0 and recovered + 1e-6 >= overpayment:
        case.status = "closed_recovered"
        case.is_active = False
    else:
        case.status = "reconciling"

    # Audit
    db.add(AuditLog(
        audit_id=str(uuid4()),
        case_id=case.case_id,
        actor_user_id=current_user.user_id,
        action="RECOUPMENT_RECORDED",
        from_state=from_state,
        to_state=case.status,
        reason=f"${body.amount:.2f} via {body.method}"
               + (f" (ref {body.reference_number})" if body.reference_number else "")
               + f"; recovered {recovered:.2f} of {overpayment:.2f}",
        meta_json="{}",
        created_at=now,
    ))

    await db.commit()
    return _to_read(rec, current_user.full_name)


@router.get("/{case_id}/recoupments", response_model=List[RecoupmentRead])
async def list_recoupments(
    case_id: int,
    db: AsyncSession = Depends(get_db),
) -> List[RecoupmentRead]:
    case_res = await db.execute(select(OpaCase).where(OpaCase.case_sequence == case_id))
    case = case_res.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    res = await db.execute(
        select(RecoupmentAction).where(RecoupmentAction.case_id == case.case_id)
        .order_by(RecoupmentAction.created_at.desc())
    )
    rows = list(res.scalars().all())

    # Bulk-load recorder names
    recorder_ids = set()
    parsed: list = []
    for r in rows:
        meta = {}
        if r.staging_output_json:
            try: meta = json.loads(r.staging_output_json)
            except Exception: meta = {}
        if meta.get("recorded_by_user_id"):
            recorder_ids.add(meta["recorded_by_user_id"])
        parsed.append((r, meta))
    user_lookup: dict = {}
    if recorder_ids:
        ures = await db.execute(select(OpaUser).where(OpaUser.user_id.in_(recorder_ids)))
        user_lookup = {u.user_id: u for u in ures.scalars().all()}

    out: List[RecoupmentRead] = []
    for r, meta in parsed:
        user = user_lookup.get(meta.get("recorded_by_user_id"))
        out.append(_to_read(r, user.full_name if user else None))
    return out
