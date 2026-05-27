"""Notification emission helpers (Phase 3).

Keep this small: a single `notify()` helper + a `notify_supervisors()` fan-out.
Callers (route handlers, case_service) emit notifications inline; no async
worker, no event bus — we just write rows to the table inside the same DB
transaction so writes commit together.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.workflow import Notification, OpaUser


async def notify(
    session: AsyncSession,
    *,
    recipient_user_id: str,
    kind: str,
    title: str,
    body: Optional[str] = None,
    case_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    link: Optional[str] = None,
) -> Notification:
    """Insert a single notification row. Caller is responsible for commit."""
    n = Notification(
        notification_id=str(uuid4()),
        recipient_user_id=recipient_user_id,
        kind=kind,
        case_id=case_id,
        actor_user_id=actor_user_id,
        title=title,
        body=body,
        link=link,
        is_read=False,
        created_at=datetime.utcnow().isoformat(),
    )
    session.add(n)
    return n


async def notify_supervisors(
    session: AsyncSession,
    *,
    kind: str,
    title: str,
    body: Optional[str] = None,
    case_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    link: Optional[str] = None,
) -> int:
    """Fan-out to every supervisor (and admin) user. Returns count emitted."""
    res = await session.execute(
        select(OpaUser).where(OpaUser.role.in_(("supervisor", "admin")))
        .where(OpaUser.is_active == True)  # noqa: E712
    )
    count = 0
    for u in res.scalars().all():
        # don't notify the actor about their own action
        if u.user_id == actor_user_id:
            continue
        await notify(
            session,
            recipient_user_id=u.user_id,
            kind=kind, title=title, body=body,
            case_id=case_id, actor_user_id=actor_user_id, link=link,
        )
        count += 1
    return count
