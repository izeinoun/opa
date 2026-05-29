from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from ..middleware.auth import require_app
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.reference import Member

router = APIRouter(prefix="/api/members", tags=["members"], dependencies=[Depends(require_app("payguard"))])


# ── Schemas ──────────────────────────────────────────────────────────────────

class MemberIn(BaseModel):
    member_number: str
    first_name: str
    last_name: str
    date_of_birth: str
    lob: str
    coverage_effective_date: str
    coverage_termination_date: Optional[str] = None


class MemberOut(BaseModel):
    member_id: str
    member_number: str
    first_name: str
    last_name: str
    date_of_birth: str
    lob: str
    coverage_effective_date: str
    coverage_termination_date: Optional[str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


def _to_out(m: Member) -> MemberOut:
    return MemberOut(
        member_id=m.member_id,
        member_number=m.member_number,
        first_name=m.first_name,
        last_name=m.last_name,
        date_of_birth=m.date_of_birth,
        lob=m.lob,
        coverage_effective_date=m.coverage_effective_date,
        coverage_termination_date=m.coverage_termination_date,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=dict)
async def list_members(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: Optional[str] = None,
    lob: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    query = select(Member)
    count_query = select(func.count()).select_from(Member)

    if search:
        pattern = f"%{search}%"
        search_filter = or_(
            Member.member_number.ilike(pattern),
            Member.first_name.ilike(pattern),
            Member.last_name.ilike(pattern),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    if lob:
        query = query.where(Member.lob == lob)
        count_query = count_query.where(Member.lob == lob)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    members = result.scalars().all()

    return {"total": total, "items": [_to_out(m) for m in members]}


@router.post("", response_model=MemberOut, status_code=201)
async def create_member(
    body: MemberIn,
    db: AsyncSession = Depends(get_db),
) -> MemberOut:
    existing = await db.execute(
        select(Member).where(Member.member_number == body.member_number)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Member number '{body.member_number}' already exists")

    now = datetime.utcnow().isoformat()
    member = Member(
        member_id=str(uuid4()),
        member_number=body.member_number,
        first_name=body.first_name,
        last_name=body.last_name,
        date_of_birth=body.date_of_birth,
        lob=body.lob,
        coverage_effective_date=body.coverage_effective_date,
        coverage_termination_date=body.coverage_termination_date,
        created_at=now,
        updated_at=now,
    )
    db.add(member)
    await db.flush()
    return _to_out(member)


@router.put("/{member_id}", response_model=MemberOut)
async def update_member(
    member_id: str,
    body: MemberIn,
    db: AsyncSession = Depends(get_db),
) -> MemberOut:
    result = await db.execute(select(Member).where(Member.member_id == member_id))
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    if body.member_number != member.member_number:
        conflict = await db.execute(
            select(Member).where(Member.member_number == body.member_number)
        )
        if conflict.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail=f"Member number '{body.member_number}' already exists")

    member.member_number = body.member_number
    member.first_name = body.first_name
    member.last_name = body.last_name
    member.date_of_birth = body.date_of_birth
    member.lob = body.lob
    member.coverage_effective_date = body.coverage_effective_date
    member.coverage_termination_date = body.coverage_termination_date
    member.updated_at = datetime.utcnow().isoformat()

    await db.flush()
    return _to_out(member)


@router.delete("/{member_id}", status_code=204)
async def delete_member(
    member_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(select(Member).where(Member.member_id == member_id))
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    await db.delete(member)
    await db.flush()
