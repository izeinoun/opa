from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..models.claims import Claim
from ..schemas.case_schemas import ClaimFindingRead

router = APIRouter(prefix="/api/claims", tags=["claims"])


@router.get("", response_model=list)
async def list_claims(
    lob: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list:
    stmt = select(Claim)
    if lob:
        stmt = stmt.where(Claim.lob == lob)
    skip = (page - 1) * page_size
    stmt = stmt.offset(skip).limit(page_size)
    result = await db.execute(stmt)
    claims = result.scalars().all()
    return [
        {
            "id": c.claim_id,
            "claim_number": c.icn,
            "lob": c.lob,
            "total_billed": c.total_billed,
            "total_paid": c.total_paid,
            "status": c.claim_status,
            "service_date_start": c.service_from_date,
        }
        for c in claims
    ]


@router.get("/{claim_id}", response_model=dict)
async def get_claim(claim_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(Claim).where(Claim.claim_id == claim_id))
    claim = result.scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")
    return {
        "id": claim.claim_id,
        "claim_number": claim.icn,
        "lob": claim.lob,
        "total_billed": claim.total_billed,
        "total_paid": claim.total_paid,
        "status": claim.claim_status,
        "service_date_start": claim.service_from_date,
    }
