"""POST /api/analyze/835 — parse a raw X12 835, create a case, run detectors, return CaseDetail.

The heavy lifting lives in services/case_creation_service.py so the file-intake
"drop an 835 file" path and this paste-EDI path share one implementation.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import require_app
from ..schemas.case_schemas import CaseDetail
from ..services.case_creation_service import create_case_from_835

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analyze", tags=["analyze"], dependencies=[Depends(require_app("payguard"))])


class Analyze835Request(BaseModel):
    raw_edi: str


@router.post("/835", response_model=CaseDetail)
async def analyze_835(
    body: Analyze835Request,
    db: AsyncSession = Depends(get_db),
) -> CaseDetail:
    result = await create_case_from_835(db, body.raw_edi)
    return result.detail
