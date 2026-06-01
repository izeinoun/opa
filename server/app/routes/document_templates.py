"""Generic LLM document templates + PDF generation — shared by both apps.

  CRUD on templates ............ admin only (require_role('admin'))
  list / generate .............. any app user (require_any_app)

Templates are partitioned by the `app` discriminator; every endpoint that
takes an `app` validates it against the allowed set.
"""
from __future__ import annotations

import base64
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user, require_any_app, require_role
from ..dao.document_template_dao import DocumentTemplateDAO
from ..models.workflow import DocumentTemplate, OpaUser
from ..schemas.document_template_schemas import (
    DocumentTemplateCreate,
    DocumentTemplateRead,
    GenerateDocumentRequest,
    GenerateDocumentResponse,
)
from ..services.document_generation_service import (
    DocumentGenerationError,
    DocumentGenerationService,
)

router = APIRouter(prefix="/api/document-templates", tags=["document-templates"])

_ALLOWED_APPS = {"payguard", "claimguard"}


def _validate_app(app: str) -> str:
    if app not in _ALLOWED_APPS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown app '{app}'; expected one of {sorted(_ALLOWED_APPS)}",
        )
    return app


def _to_read(t: DocumentTemplate) -> DocumentTemplateRead:
    return DocumentTemplateRead(
        template_id=t.template_id,
        app=t.app,
        name=t.name,
        description=t.description,
        task_prompt=t.task_prompt,
        template_markdown=t.template_markdown,
        version=t.version,
        is_active=t.is_active,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


# ── Template CRUD (admin) ─────────────────────────────────────────────────

@router.get("", response_model=List[DocumentTemplateRead])
async def list_templates(
    app: str = Query(...),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    _user: OpaUser = Depends(require_any_app("payguard", "claimguard")),
) -> List[DocumentTemplateRead]:
    _validate_app(app)
    rows = await DocumentTemplateDAO(db).list_for_app(app, active_only=active_only)
    return [_to_read(r) for r in rows]


@router.get("/{template_id}", response_model=DocumentTemplateRead)
async def get_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    _user: OpaUser = Depends(require_any_app("payguard", "claimguard")),
) -> DocumentTemplateRead:
    row = await DocumentTemplateDAO(db).get_by_id(template_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return _to_read(row)


@router.post("", response_model=DocumentTemplateRead, status_code=201)
async def create_template(
    payload: DocumentTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: OpaUser = Depends(require_role("admin")),
) -> DocumentTemplateRead:
    _validate_app(payload.app)
    row = await DocumentTemplateDAO(db).create(
        DocumentTemplate(
            app=payload.app,
            name=payload.name,
            description=payload.description,
            task_prompt=payload.task_prompt,
            template_markdown=payload.template_markdown,
            is_active=payload.is_active,
            created_by_user_id=user.user_id,
        )
    )
    return _to_read(row)


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    _user: OpaUser = Depends(require_role("admin")),
) -> Response:
    dao = DocumentTemplateDAO(db)
    row = await dao.get_by_id(template_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    await dao.delete(row)
    return Response(status_code=204)


# ── Generation ────────────────────────────────────────────────────────────

async def _generate(payload: GenerateDocumentRequest, db: AsyncSession):
    _validate_app(payload.app)
    try:
        return await DocumentGenerationService(db).generate(
            app=payload.app,
            content=payload.content,
            template_id=payload.template_id,
            template_markdown=payload.template_markdown,
            task_prompt=payload.task_prompt,
        )
    except DocumentGenerationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/generate")
async def generate_pdf(
    payload: GenerateDocumentRequest,
    db: AsyncSession = Depends(get_db),
    _user: OpaUser = Depends(require_any_app("payguard", "claimguard")),
) -> Response:
    """Generate a document and stream it back as a PDF (application/pdf)."""
    doc = await _generate(payload, db)
    filename = f"{doc.template_id or payload.app}.pdf"
    return Response(
        content=doc.pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/generate-json", response_model=GenerateDocumentResponse)
async def generate_json(
    payload: GenerateDocumentRequest,
    db: AsyncSession = Depends(get_db),
    _user: OpaUser = Depends(require_any_app("payguard", "claimguard")),
) -> GenerateDocumentResponse:
    """Generate a document and return Markdown + base64 PDF (for preview)."""
    doc = await _generate(payload, db)
    return GenerateDocumentResponse(
        markdown=doc.markdown,
        pdf_base64=base64.b64encode(doc.pdf_bytes).decode("ascii"),
        template_id=doc.template_id,
    )
