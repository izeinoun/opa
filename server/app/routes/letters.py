from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from ..middleware.auth import require_app
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.workflow import OpaUser
from ..schemas.letter_schemas import (
    LetterTemplateRead,
    LetterTemplateDetail,
    RecoveryNoticeCreate,
    RecoveryNoticeRead,
    RenderedLetter,
)
from ..services.letter_service import LetterService

router = APIRouter(prefix="/api/letters", tags=["letters"], dependencies=[Depends(require_app("payguard"))])


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


class LetterTemplateUpdate(BaseModel):
    template_name: Optional[str] = None
    regulatory_reference: Optional[str] = None
    content_html: Optional[str] = None  # mapped to LetterTemplate.template_content
    is_active: Optional[bool] = None


@router.patch("/templates/{template_id}", response_model=LetterTemplateDetail)
async def update_template(
    template_id: str,
    body: LetterTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> LetterTemplateDetail:
    """Admin-only template edit. Updates the editable fields in-place.
    Audit-logged with old → new diff summary."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required to edit letter templates")

    from sqlalchemy import select
    from ..models.workflow import LetterTemplate, AuditLog
    from datetime import datetime
    from uuid import uuid4

    res = await db.execute(select(LetterTemplate).where(LetterTemplate.template_id == template_id))
    tmpl = res.scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")

    changes: list[str] = []
    if body.template_name is not None and body.template_name != tmpl.template_name:
        changes.append(f"name: '{tmpl.template_name}' → '{body.template_name}'")
        tmpl.template_name = body.template_name
    if body.regulatory_reference is not None and body.regulatory_reference != tmpl.regulatory_reference:
        changes.append("regulatory_reference updated")
        tmpl.regulatory_reference = body.regulatory_reference
    if body.content_html is not None and body.content_html != tmpl.template_content:
        changes.append(f"content updated ({len(tmpl.template_content or '')} → {len(body.content_html)} chars)")
        tmpl.template_content = body.content_html
    if body.is_active is not None and body.is_active != tmpl.is_active:
        changes.append(f"is_active: {tmpl.is_active} → {body.is_active}")
        tmpl.is_active = body.is_active

    if changes:
        db.add(AuditLog(
            audit_id=str(uuid4()),
            case_id=None,
            actor_user_id=current_user.user_id,
            action=f"LETTER_TEMPLATE_EDITED:{template_id}",
            from_state=None,
            to_state=None,
            reason="; ".join(changes),
            meta_json="{}",
            created_at=datetime.utcnow().isoformat(),
        ))

    await db.commit()

    service = LetterService(db)
    detail = await service.get_template_detail(template_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Template missing after update")
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
