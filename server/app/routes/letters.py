from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas.letter_schemas import (
    LetterTemplateRead,
    LetterTemplateDetail,
    RecoveryNoticeCreate,
    RecoveryNoticeRead,
    RenderedLetter,
)
from ..services.letter_service import LetterService

router = APIRouter(prefix="/api/letters", tags=["letters"])


@router.get("/templates", response_model=List[LetterTemplateRead])
async def list_templates(
    lob: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> List[LetterTemplateRead]:
    service = LetterService(db)
    return await service.get_templates(lob=lob)


@router.get("/templates/{template_id}", response_model=LetterTemplateDetail)
async def get_template(
    template_id: str, db: AsyncSession = Depends(get_db)
) -> LetterTemplateDetail:
    service = LetterService(db)
    detail = await service.get_template_detail(template_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return detail


@router.post("/render", response_model=RenderedLetter)
async def render_letter(
    body: dict, db: AsyncSession = Depends(get_db)
) -> RenderedLetter:
    case_id = body.get("case_id")
    template_code = body.get("template_code")
    if not case_id or not template_code:
        raise HTTPException(status_code=400, detail="case_id and template_code are required")

    service = LetterService(db)
    try:
        return await service.render_letter(int(case_id), str(template_code))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/notices", response_model=RecoveryNoticeRead, status_code=201)
async def send_notice(
    body: RecoveryNoticeCreate, db: AsyncSession = Depends(get_db)
) -> RecoveryNoticeRead:
    service = LetterService(db)
    try:
        return await service.send_notice(body)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/send", response_model=RecoveryNoticeRead, status_code=201)
async def send_notice_alias(
    body: RecoveryNoticeCreate, db: AsyncSession = Depends(get_db)
) -> RecoveryNoticeRead:
    """Alias for /notices — matches frontend letterService.ts."""
    service = LetterService(db)
    try:
        return await service.send_notice(body)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/notices/{case_id}", response_model=List[RecoveryNoticeRead])
async def get_notices(
    case_id: int, db: AsyncSession = Depends(get_db)
) -> List[RecoveryNoticeRead]:
    service = LetterService(db)
    return await service.get_notices(case_id)
