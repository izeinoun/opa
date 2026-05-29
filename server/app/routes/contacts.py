"""Case contact log endpoints (Phase 4)."""
from datetime import datetime, date
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from ..middleware.auth import require_app
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user, assert_case_writable_by
from ..models.workflow import OpaCase, ContactLog, OpaUser


router = APIRouter(prefix="/api/cases", tags=["contacts"], dependencies=[Depends(require_app("payguard"))])

_VALID_METHODS = {"phone", "email", "letter", "in_person", "portal"}
_VALID_DIRECTIONS = {"outbound", "inbound"}


class ContactCreate(BaseModel):
    contact_date: str = Field(min_length=10, max_length=10)  # YYYY-MM-DD
    method: str
    direction: str
    participant_name: Optional[str] = None
    summary: str


class ContactRead(BaseModel):
    id: str
    contact_date: str
    method: str
    direction: str
    participant_name: Optional[str] = None
    summary: str
    logged_by_full_name: Optional[str] = None
    created_at: str


def _to_read(c: ContactLog) -> ContactRead:
    return ContactRead(
        id=c.contact_id,
        contact_date=c.contact_date,
        method=c.method,
        direction=c.direction,
        participant_name=c.participant_name,
        summary=c.summary,
        logged_by_full_name=c.logger.full_name if c.logger else None,
        created_at=c.created_at,
    )


@router.get("/{case_id}/contacts", response_model=List[ContactRead])
async def list_contacts(case_id: int, db: AsyncSession = Depends(get_db)) -> List[ContactRead]:
    case_res = await db.execute(select(OpaCase).where(OpaCase.case_sequence == case_id))
    case = case_res.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    res = await db.execute(
        select(ContactLog).where(ContactLog.case_id == case.case_id)
        .order_by(ContactLog.contact_date.desc(), ContactLog.created_at.desc())
    )
    return [_to_read(c) for c in res.scalars().all()]


@router.post("/{case_id}/contacts", response_model=ContactRead, status_code=201)
async def add_contact(
    case_id: int,
    body: ContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> ContactRead:
    if body.method not in _VALID_METHODS:
        raise HTTPException(status_code=400, detail=f"method must be one of {sorted(_VALID_METHODS)}")
    if body.direction not in _VALID_DIRECTIONS:
        raise HTTPException(status_code=400, detail=f"direction must be one of {sorted(_VALID_DIRECTIONS)}")
    if not body.summary or not body.summary.strip():
        raise HTTPException(status_code=400, detail="Summary cannot be empty")
    try:
        date.fromisoformat(body.contact_date)
    except Exception:
        raise HTTPException(status_code=400, detail="contact_date must be YYYY-MM-DD")

    case_res = await db.execute(select(OpaCase).where(OpaCase.case_sequence == case_id))
    case = case_res.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    assert_case_writable_by(case, current_user)

    c = ContactLog(
        contact_id=str(uuid4()),
        case_id=case.case_id,
        logged_by_user_id=current_user.user_id,
        contact_date=body.contact_date,
        method=body.method,
        direction=body.direction,
        participant_name=(body.participant_name or "").strip() or None,
        summary=body.summary.strip(),
        created_at=datetime.utcnow().isoformat(),
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return _to_read(c)
