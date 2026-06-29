import json
import logging
from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from ..middleware.auth import require_any_app, require_role
from pydantic import BaseModel
from sqlalchemy import select, func, or_, literal
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.reference import Member
from ..models.workflow import OpaCase
from ..models.claims import Claim
from ..services.assistant.clearlink_integration import call_clearlink_tool

logger = logging.getLogger(__name__)

# Members are shared reference data — every app needs to look them up
# (post-pay case grouping, pre-pay intake validation, IAM admin management).
# Reads: open to any app the caller has access to.
# Writes (POST/PUT/DELETE): admin role only, enforced per-route.
router = APIRouter(
    prefix="/api/members",
    tags=["members"],
    dependencies=[Depends(require_any_app("payguard", "claimguard"))],
)


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
        full_name = func.concat(Member.first_name, literal(" "), Member.last_name)
        search_filter = or_(
            Member.member_number.ilike(pattern),
            Member.first_name.ilike(pattern),
            Member.last_name.ilike(pattern),
            full_name.ilike(pattern),
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


@router.get("/{member_id}/360")
async def get_member_360(
    member_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cross-system member profile: member demographics + PayGuard post-pay cases
    + ClaimGuard pre-pay claims + ClearLink eligibility (when configured)."""
    member_res = await db.execute(select(Member).where(Member.member_id == member_id))
    member = member_res.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    # PayGuard: post-pay overpayment cases for this member
    pg_res = await db.execute(
        select(OpaCase)
        .where(OpaCase.member_id == member_id, OpaCase.pipeline_mode == "post_pay")
        .order_by(OpaCase.case_sequence.desc())
        .limit(10)
    )
    pg_cases = pg_res.scalars().all()

    # ClaimGuard: pre-pay claims for this member
    cg_res = await db.execute(
        select(Claim)
        .where(Claim.member_id == member_id, Claim.pipeline_mode == "pre_pay")
        .order_by(Claim.service_from_date.desc())
        .limit(10)
    )
    cg_claims = cg_res.scalars().all()

    # ClearLink: member demographics (optional — graceful fallback when not configured)
    cl_ok, cl_body = await call_clearlink_tool("get_member_demographics", {"member_id": member.member_number})
    try:
        cl_data = json.loads(cl_body) if cl_ok else None
    except Exception:
        cl_data = None

    return {
        "member": _to_out(member).model_dump(),
        "payguard": {
            "total": len(pg_cases),
            "cases": [
                {
                    "case_id": c.case_id,
                    "case_number": f"OPA-{c.created_at[:4]}-{c.case_sequence:05d}" if c.case_sequence else c.case_id,
                    "status": c.status,
                    "priority": c.priority,
                    "total_overpayment_amount": c.total_overpayment_amount,
                    "created_at": c.created_at,
                }
                for c in pg_cases
            ],
        },
        "claimguard": {
            "total": len(cg_claims),
            "claims": [
                {
                    "claim_id": c.claim_id,
                    "icn": c.icn if hasattr(c, "icn") else c.claim_id,
                    "status": c.claim_status,
                    "billed_amount": c.billed_amount,
                    "service_from_date": c.service_from_date,
                }
                for c in cg_claims
            ],
        },
        "clearlink": {
            "available": cl_ok,
            "demographics": cl_data,
        },
    }


@router.post("", response_model=MemberOut, status_code=201,
             dependencies=[Depends(require_role("admin"))])
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


@router.put("/{member_id}", response_model=MemberOut,
            dependencies=[Depends(require_role("admin"))])
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


@router.delete("/{member_id}", status_code=204,
               dependencies=[Depends(require_role("admin"))])
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
