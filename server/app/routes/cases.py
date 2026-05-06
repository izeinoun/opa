from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.workflow import OpaCase, OpaUser
from ..schemas.case_schemas import (
    CaseDetail,
    CaseCreate,
    CaseTransition,
    CaseListResponse,
    WorklistFilters,
    AuditLogRead,
    RecoveryNoticeRead,
)
from ..services.case_service import CaseService
from ..services.letter_service import LetterService
from ..services.detector_service import DetectorService

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.get("", response_model=CaseListResponse)
async def list_cases(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    lob: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    exclude_closed: bool = Query(False),
    closed_only: bool = Query(False),
    overdue_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> CaseListResponse:
    filters = WorklistFilters(
        status=status, priority=priority, lob=lob, search=search,
        exclude_closed=exclude_closed, closed_only=closed_only,
        overdue_only=overdue_only,
    )
    skip = (page - 1) * page_size
    service = CaseService(db)
    return await service.get_worklist(filters, skip=skip, limit=page_size, page=page)


@router.get("/{case_id}", response_model=CaseDetail)
async def get_case(case_id: int, db: AsyncSession = Depends(get_db)) -> CaseDetail:
    service = CaseService(db)
    try:
        return await service.get_case_detail(case_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{case_id}/transition", response_model=CaseDetail)
async def transition_case(
    case_id: int,
    body: CaseTransition,
    db: AsyncSession = Depends(get_db),
) -> CaseDetail:
    service = CaseService(db)
    try:
        return await service.transition(case_id, body, acting_user_id=None)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{case_id}/reopen", response_model=CaseDetail)
async def reopen_case(
    case_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> CaseDetail:
    reason = body.get("reason", "")
    service = CaseService(db)
    try:
        return await service.reopen(case_id, supervisor_id=None, reason=reason)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{case_id}/rerun-detectors")
async def rerun_detectors(
    case_id: int, db: AsyncSession = Depends(get_db)
) -> dict:
    service = DetectorService(db)
    try:
        return await service.run_for_case(case_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class AssignRequest(BaseModel):
    analyst_id: Optional[str] = None  # None = unassign


@router.patch("/{case_id}/assign", response_model=CaseDetail)
async def assign_case(
    case_id: int,
    body: AssignRequest,
    db: AsyncSession = Depends(get_db),
) -> CaseDetail:
    case_res = await db.execute(select(OpaCase).where(OpaCase.case_sequence == case_id))
    case = case_res.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    if body.analyst_id is not None:
        user_res = await db.execute(select(OpaUser).where(OpaUser.user_id == body.analyst_id))
        user = user_res.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="Analyst not found")

    case.assigned_analyst_id = body.analyst_id
    if body.analyst_id and case.status == "new":
        case.status = "assigned"

    await db.flush()
    service = CaseService(db)
    return await service.get_case_detail(case_id)


@router.get("/{case_id}/notices", response_model=List[RecoveryNoticeRead])
async def get_case_notices(
    case_id: int, db: AsyncSession = Depends(get_db)
) -> List[RecoveryNoticeRead]:
    service = LetterService(db)
    return await service.get_notices(case_id)
