"""Lightweight user picker endpoint — read-only.

ClaimGuard's frontend uses GET /users to populate the current-user picker
in the top bar and the analyst-assignment dropdowns. This shape mirrors what
the UI expects (ClaimGuard's User type) so the frontend can re-point with
minimal change.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.workflow import OpaUser
from ..schemas.prepay_schemas import UserOut

router = APIRouter(prefix="/api/users", tags=["users"])


def _to_out(u: OpaUser) -> UserOut:
    return UserOut(
        id=u.user_id,
        name=u.full_name,
        role=u.role,
        initials=u.initials,
        color_hex=u.color_hex,
        specialty=u.specialty,
        supervisor_id=u.supervisor_id,
    )


@router.get("", response_model=List[UserOut])
async def list_users(db: AsyncSession = Depends(get_db)) -> List[UserOut]:
    res = await db.execute(
        select(OpaUser).where(OpaUser.is_active == True).order_by(OpaUser.full_name)  # noqa: E712
    )
    return [_to_out(u) for u in res.scalars().all()]


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: str, db: AsyncSession = Depends(get_db)) -> UserOut:
    res = await db.execute(select(OpaUser).where(OpaUser.user_id == user_id))
    u = res.scalar_one_or_none()
    if u is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_out(u)
