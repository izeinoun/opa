"""Document upload + retrieval endpoints. Ported from ClaimGuard's
routers/documents.py and adapted to the unified `documents` table.

Endpoints:
  POST   /api/documents               Upload a document (claim_id and/or case_id in form)
  GET    /api/documents?claim_id=...  List documents for a claim
  GET    /api/documents?case_id=...   List documents for a case
  GET    /api/documents/{id}/download Stream the file back
  DELETE /api/documents/{id}          Remove a document row + file
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.claims import Claim
from ..models.workflow import AuditLog, Document, OpaCase
from ..schemas.prepay_schemas import DocumentOut
from ..services.prepay_intake_service import UPLOAD_DIR, safe_filename

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])


def _to_out(d: Document) -> DocumentOut:
    return DocumentOut(
        id=d.document_id,
        claim_id=d.claim_id,
        case_id=d.case_id,
        filename=d.filename,
        file_size_kb=d.file_size_kb,
        kind=d.kind,
        uploaded_at=d.uploaded_at,
        uploaded_by_user_id=d.uploaded_by_user_id,
    )


@router.get("", response_model=List[DocumentOut])
async def list_documents(
    claim_id: Optional[str] = None,
    case_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> List[DocumentOut]:
    if not claim_id and not case_id:
        raise HTTPException(status_code=400, detail="claim_id or case_id required")
    stmt = select(Document)
    if claim_id:
        stmt = stmt.where(Document.claim_id == claim_id)
    if case_id:
        stmt = stmt.where(Document.case_id == case_id)
    stmt = stmt.order_by(Document.uploaded_at.desc())
    res = await db.execute(stmt)
    return [_to_out(d) for d in res.scalars().all()]


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    claim_id: Optional[str] = Form(None),
    case_id: Optional[str] = Form(None),
    user_id: Optional[str] = Form(None),
    kind: str = Form("supporting"),
    db: AsyncSession = Depends(get_db),
) -> DocumentOut:
    if not claim_id and not case_id:
        raise HTTPException(status_code=400, detail="claim_id or case_id required")
    if claim_id:
        c = (await db.execute(
            select(Claim).where(Claim.claim_id == claim_id)
        )).scalar_one_or_none()
        if c is None:
            raise HTTPException(status_code=404, detail="Claim not found")
    if case_id:
        kc = (await db.execute(
            select(OpaCase).where(OpaCase.case_id == case_id)
        )).scalar_one_or_none()
        if kc is None:
            raise HTTPException(status_code=404, detail="Case not found")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")

    original = safe_filename(file.filename or "upload.pdf")
    scope = (claim_id or case_id)[:8]
    stored_name = f"{scope}_{uuid.uuid4().hex[:8]}_{original}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / stored_name
    dest.write_bytes(raw)
    size_kb = max(1, len(raw) // 1024)
    now = datetime.utcnow().isoformat()

    doc = Document(
        document_id=str(uuid.uuid4()),
        claim_id=claim_id,
        case_id=case_id,
        filename=stored_name,
        file_path=str(dest),
        file_size_kb=size_kb,
        kind=kind if kind in {"claim_form", "supporting", "medical_record"} else "supporting",
        uploaded_at=now,
        uploaded_by_user_id=user_id,
    )
    db.add(doc)
    if claim_id:
        db.add(AuditLog(
            audit_id=str(uuid.uuid4()),
            case_id=case_id,
            claim_id=claim_id,
            actor_user_id=user_id or "system",
            action=f"Document uploaded: {original} ({size_kb} KB)",
            from_state=None, to_state=None, reason=None,
            meta_json="{}",
            created_at=now,
        ))
    await db.commit()
    return _to_out(doc)


@router.get("/{document_id}/download")
async def download_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    d = (await db.execute(
        select(Document).where(Document.document_id == document_id)
    )).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail="Document not found")
    p = Path(d.file_path)
    if not p.exists():
        raise HTTPException(status_code=410, detail="File missing from disk")
    return FileResponse(path=str(p), filename=d.filename, media_type="application/octet-stream")


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    user_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> None:
    d = (await db.execute(
        select(Document).where(Document.document_id == document_id)
    )).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail="Document not found")
    Path(d.file_path).unlink(missing_ok=True)
    await db.delete(d)
    await db.commit()
