"""Notification feed endpoints (Phase 3)."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from ..middleware.auth import require_any_app
from pydantic import BaseModel
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.workflow import Notification, OpaCase, OpaUser


router = APIRouter(prefix="/api/notifications", tags=["notifications"], dependencies=[Depends(require_any_app("payguard", "claimguard", "fwa", "cob"))])


class NotificationActor(BaseModel):
    id: str
    full_name: str
    role: str


class NotificationRead(BaseModel):
    id: str
    kind: str
    title: str
    body: Optional[str] = None
    link: Optional[str] = None
    case_id: Optional[str] = None
    case_number: Optional[str] = None
    case_sequence: Optional[int] = None
    actor: Optional[NotificationActor] = None
    is_read: bool
    created_at: str


def _to_read(n: Notification, case_lookup: dict) -> NotificationRead:
    case = case_lookup.get(n.case_id) if n.case_id else None
    return NotificationRead(
        id=n.notification_id,
        kind=n.kind,
        title=n.title,
        body=n.body,
        link=n.link,
        case_id=n.case_id,
        case_number=case.case_number if case else None,
        case_sequence=case.case_sequence if case else None,
        actor=(
            NotificationActor(id=n.actor.user_id, full_name=n.actor.full_name, role=n.actor.role)
            if n.actor else None
        ),
        is_read=n.is_read,
        created_at=n.created_at,
    )


@router.get("", response_model=List[NotificationRead])
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> List[NotificationRead]:
    stmt = (
        select(Notification)
        .where(Notification.recipient_user_id == current_user.user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(Notification.is_read == False)  # noqa: E712

    res = await db.execute(stmt)
    rows = list(res.scalars().all())

    # Bulk-load referenced cases
    case_ids = {n.case_id for n in rows if n.case_id}
    case_lookup: dict = {}
    if case_ids:
        cres = await db.execute(select(OpaCase).where(OpaCase.case_id.in_(case_ids)))
        case_lookup = {c.case_id: c for c in cres.scalars().all()}

    return [_to_read(n, case_lookup) for n in rows]


@router.get("/count")
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> dict:
    res = await db.execute(
        select(func.count(Notification.notification_id))
        .where(Notification.recipient_user_id == current_user.user_id)
        .where(Notification.is_read == False)  # noqa: E712
    )
    return {"unread": int(res.scalar_one() or 0)}


@router.post("/{notification_id}/read", response_model=NotificationRead)
async def mark_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> NotificationRead:
    res = await db.execute(
        select(Notification).where(Notification.notification_id == notification_id)
    )
    n = res.scalar_one_or_none()
    if n is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if n.recipient_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not your notification")
    n.is_read = True
    await db.commit()
    case_lookup: dict = {}
    if n.case_id:
        cres = await db.execute(select(OpaCase).where(OpaCase.case_id == n.case_id))
        c = cres.scalar_one_or_none()
        if c:
            case_lookup[c.case_id] = c
    return _to_read(n, case_lookup)


@router.post("/mark-all-read")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> dict:
    res = await db.execute(
        update(Notification)
        .where(Notification.recipient_user_id == current_user.user_id)
        .where(Notification.is_read == False)  # noqa: E712
        .values(is_read=True)
    )
    await db.commit()
    return {"updated": res.rowcount or 0}
