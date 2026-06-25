"""File Intake — simulated drop-folder ingestion (Administrator-only).

Mirrors the production pattern where files are dropped into a storage location
and the app picks them up. Here, an admin uploads into "folders" on the File
Intake page; each upload is processed immediately and routed by category:

  PayGuard (post-pay)
    835      X12 ERA       → CREATE a case (services.case_creation_service)
    837      X12 claim     → MATCH member + service date → LINK to a case
    medical  clinical PDF  → LLM-extract ids → MATCH → LINK to a case
  ClaimGuard (pre-pay)
    claim_pdf  CMS-1500/1450 PDF → existing pre-pay PDF intake (LLM extract)

837s / medical records that match 0 or >1 cases park as status='unmatched' for
resolution via the Unmatched queue (POST /{intake_id}/resolve).

Every upload is recorded in `intake_files`; the durable `documents` row is only
written once a case is created or matched.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import require_role
from ..models.claims import Claim
from ..models.reference import Member
from ..models.workflow import AuditLog, Document, IntakeFile, OpaCase, OpaUser
from ..schemas.intake_schemas import (
    CandidateCaseOut,
    IntakeFileOut,
    OutputFileOut,
    ResolveRequest,
    UnmatchedOut,
)
from ..services import ai_service
from ..services.case_creation_service import create_case_from_835
from ..services.claim_enrichment_service import enrich_claim_from_837
from ..services.edi_parser_837 import parse_837
from ..services.intake_matching_service import match_to_case
from ..services.reevaluation_service import reevaluate_case
from ..services.pdf_extraction_service import extract_text as extract_pdf_text
from ..services.prepay_intake_service import (
    IntakeValidationError,
    UPLOAD_DIR,
    ingest_extracted_claim,
    safe_filename,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/file-intake",
    tags=["file-intake"],
    dependencies=[Depends(require_role("admin", "intake"))],
)

INTAKE_DIR = UPLOAD_DIR / "intake"

# Valid (app, category) combinations.
_VALID_COMBOS = {
    ("payguard", "835"),
    ("payguard", "837"),
    ("payguard", "medical"),
    ("claimguard", "claim_pdf"),
}


# ── Serialization ──────────────────────────────────────────────────────────

def _json_list(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        v = json.loads(raw)
        return [str(x) for x in v] if isinstance(v, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _json_service_lines(raw: Optional[str]) -> List[dict]:
    """Parse the persisted JSON list of {cpt, date} per-line pairs."""
    if not raw:
        return []
    try:
        v = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(v, list):
        return []
    return [
        {"cpt": it.get("cpt"), "date": it.get("date")}
        for it in v if isinstance(it, dict)
    ]


async def _to_out(db: AsyncSession, row: IntakeFile) -> IntakeFileOut:
    case_number = None
    case_sequence = None
    if row.result_case_id:
        c = (await db.execute(
            select(OpaCase.case_number, OpaCase.case_sequence)
            .where(OpaCase.case_id == row.result_case_id)
        )).first()
        if c:
            case_number, case_sequence = c
    return IntakeFileOut(
        intake_id=row.intake_id,
        app=row.app,
        category=row.category,
        filename=row.filename,
        file_size_kb=row.file_size_kb,
        uploaded_at=row.uploaded_at,
        uploaded_by_user_id=row.uploaded_by_user_id,
        extraction_status=row.extraction_status,
        extracted_member_number=row.extracted_member_number,
        extracted_member_name=row.extracted_member_name,
        extracted_dob=row.extracted_dob,
        extracted_service_dates=_json_list(row.extracted_service_dates),
        extracted_service_lines=_json_service_lines(row.extracted_service_lines),
        status=row.status,
        candidate_case_ids=_json_list(row.candidate_case_ids),
        message=row.message,
        result_case_id=row.result_case_id,
        result_claim_id=row.result_claim_id,
        result_document_id=row.result_document_id,
        result_case_number=case_number,
        result_case_sequence=case_sequence,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ── Document attachment + audit helpers ────────────────────────────────────

async def _attach_document(
    db: AsyncSession,
    *,
    intake: IntakeFile,
    case_id: str,
    claim_id: Optional[str],
    kind: str,
    extracted_text: Optional[str] = None,
    page_count: Optional[int] = None,
) -> Document:
    """Create the durable `documents` row pointing at the already-stored intake
    file, linked to the resolved case (and claim when known)."""
    now = datetime.utcnow().isoformat()
    doc = Document(
        document_id=str(uuid.uuid4()),
        claim_id=claim_id,
        case_id=case_id,
        filename=intake.filename,
        file_path=intake.file_path,
        file_size_kb=intake.file_size_kb,
        kind=kind,
        uploaded_at=now,
        uploaded_by_user_id=intake.uploaded_by_user_id,
        extracted_text=extracted_text,
        extracted_at=now if extracted_text is not None else None,
        extraction_status=("complete" if extracted_text else "failed") if extracted_text is not None else None,
        page_count=page_count,
    )
    db.add(doc)
    db.add(AuditLog(
        audit_id=str(uuid.uuid4()),
        case_id=case_id,
        claim_id=claim_id,
        actor_user_id=intake.uploaded_by_user_id or "system",
        action=f"File Intake: {intake.category} document linked ({intake.filename})",
        from_state=None, to_state=None, reason=None,
        meta_json="{}",
        created_at=now,
    ))
    return doc


# ── Per-category processing ────────────────────────────────────────────────

async def _process_835(db: AsyncSession, intake: IntakeFile, raw: bytes) -> None:
    text = raw.decode("utf-8", errors="replace")
    try:
        created = await create_case_from_835(db, text)
    except HTTPException as e:
        intake.status = "error"
        intake.message = f"835 parse/creation failed: {e.detail}"
        intake.updated_at = datetime.utcnow().isoformat()
        await db.commit()
        return

    # A remittance may pay several claims → one case each. Attach the 835 to
    # every created case; surface the first on the intake row and list all in
    # the message.
    first_doc_id = None
    for cr in created:
        doc = await _attach_document(
            db, intake=intake, case_id=cr.case_id,
            claim_id=cr.claim_id, kind="supporting",
        )
        if first_doc_id is None:
            first_doc_id = doc.document_id
    await db.flush()
    intake.status = "case_created"
    if len(created) == 1:
        intake.message = f"Created case {created[0].case_number}"
    else:
        nums = ", ".join(c.case_number for c in created)
        intake.message = f"Created {len(created)} cases from remittance: {nums}"
    intake.result_case_id = created[0].case_id
    intake.result_claim_id = created[0].claim_id
    intake.result_document_id = first_doc_id
    intake.updated_at = datetime.utcnow().isoformat()
    await db.commit()


async def _process_837(db: AsyncSession, intake: IntakeFile, raw: bytes) -> None:
    text = raw.decode("utf-8", errors="replace")
    parsed = parse_837(text)
    name = f"{parsed.patient_first} {parsed.patient_last}".strip() or None
    intake.extraction_status = "complete"
    intake.extracted_member_number = parsed.member_number
    intake.extracted_member_name = name
    intake.extracted_dob = parsed.dob
    intake.extracted_service_dates = json.dumps(parsed.service_dates)

    service_lines = [(sl.cpt, sl.service_date) for sl in parsed.service_lines]
    intake.extracted_service_lines = json.dumps(
        [{"cpt": c, "date": d} for c, d in service_lines]
    )
    match = await match_to_case(
        db, member_number=parsed.member_number, member_name=name,
        dob=parsed.dob, service_dates=parsed.service_dates, service_lines=service_lines,
    )
    # On a confident match, copy the 837's diagnoses + claim-form metadata onto
    # the awaiting (835-created) claim BEFORE _finish_match re-evaluates, so the
    # deferred diagnosis-dependent detectors run against real Dx.
    if match.status == "matched" and match.claim_id:
        try:
            await enrich_claim_from_837(
                db, claim_id=match.claim_id, parsed=parsed,
                actor_user_id=intake.uploaded_by_user_id,
            )
        except Exception as e:  # noqa: BLE001 — never block the link on enrichment
            logger.exception("837 enrichment failed for claim %s: %s", match.claim_id, e)
    await _finish_match(db, intake, match, kind="supporting")


async def _process_medical(db: AsyncSession, intake: IntakeFile, raw: bytes) -> None:
    text, pages = extract_pdf_text(Path(intake.file_path))
    intake.extraction_status = "complete" if text.strip() else "failed"
    ids = await ai_service.extract_patient_identifiers(text)
    first = ids.get("first_name") or ""
    last = ids.get("last_name") or ""
    name = f"{first} {last}".strip() or None
    service_dates = ids.get("service_dates") or []
    intake.extracted_member_number = ids.get("member_number")
    intake.extracted_member_name = name
    intake.extracted_dob = ids.get("dob")
    intake.extracted_service_dates = json.dumps(service_dates)

    service_lines = [
        (it.get("cpt"), it.get("date"))
        for it in (ids.get("service_lines") or [])
        if isinstance(it, dict)
    ]
    intake.extracted_service_lines = json.dumps(
        [{"cpt": c, "date": d} for c, d in service_lines]
    )
    match = await match_to_case(
        db, member_number=ids.get("member_number"), member_name=name,
        dob=ids.get("dob"), service_dates=service_dates, service_lines=service_lines,
    )
    await _finish_match(
        db, intake, match, kind="medical_record",
        extracted_text=text, page_count=pages,
    )


async def _process_claim_pdf(db: AsyncSession, intake: IntakeFile, raw: bytes) -> None:
    text, _pages = extract_pdf_text(Path(intake.file_path))
    if not text.strip():
        intake.extraction_status = "failed"
        intake.status = "error"
        intake.message = "PDF contains no extractable text (likely an image-only scan)."
        intake.updated_at = datetime.utcnow().isoformat()
        await db.commit()
        return
    intake.extraction_status = "complete"
    try:
        extracted = await ai_service.extract_claim_from_text(text)
    except Exception as e:
        logger.exception("claim_pdf extraction failed: %s", e)
        intake.status = "error"
        intake.message = "Couldn't read the claim details from this document."
        intake.updated_at = datetime.utcnow().isoformat()
        await db.commit()
        return

    try:
        claim_id = await ingest_extracted_claim(
            db, extracted=extracted, pdf_bytes=raw,
            pdf_filename=intake.filename,
            uploaded_by_user_id=intake.uploaded_by_user_id,
        )
    except IntakeValidationError as e:
        intake.status = "error"
        intake.message = str(e)
        intake.updated_at = datetime.utcnow().isoformat()
        await db.commit()
        return

    # ingest_extracted_claim persists its own claim_form document; surface it.
    doc_id = (await db.execute(
        select(Document.document_id)
        .where(Document.claim_id == claim_id, Document.kind == "claim_form")
        .limit(1)
    )).scalar_one_or_none()

    intake.status = "case_created"
    intake.message = "Pre-pay claim created (ClaimGuard)"
    intake.result_claim_id = claim_id
    intake.result_document_id = doc_id
    intake.extracted_member_number = extracted.get("member_number")
    intake.extracted_member_name = extracted.get("patient")
    intake.extracted_dob = extracted.get("dob")
    if extracted.get("dos"):
        intake.extracted_service_dates = json.dumps([extracted["dos"]])
    intake.updated_at = datetime.utcnow().isoformat()
    await db.commit()


async def _finish_match(
    db: AsyncSession,
    intake: IntakeFile,
    match,
    *,
    kind: str,
    extracted_text: Optional[str] = None,
    page_count: Optional[int] = None,
) -> None:
    """Common tail for 837 / medical: link on a match, else park as unmatched."""
    now = datetime.utcnow().isoformat()
    if match.status == "matched" and match.case_id:
        doc = await _attach_document(
            db, intake=intake, case_id=match.case_id, claim_id=match.claim_id,
            kind=kind, extracted_text=extracted_text, page_count=page_count,
        )
        await db.flush()
        intake.status = "linked"
        intake.message = match.reason
        intake.result_case_id = match.case_id
        intake.result_claim_id = match.claim_id
        intake.result_document_id = doc.document_id
        # For medical records, append text to the claim corpus so the existing
        # evidence pipeline can use it (mirrors routes/documents.py behaviour).
        if kind == "medical_record" and extracted_text and extracted_text.strip() and match.claim_id:
            claim = (await db.execute(
                select(Claim).where(Claim.claim_id == match.claim_id)
            )).scalar_one_or_none()
            if claim is not None:
                ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
                header = f"\n[Document: {intake.filename} | {ts} | medical_record]\n{extracted_text}\n"
                claim.extracted_text = (claim.extracted_text or "") + header
    else:
        intake.status = "unmatched"
        intake.message = match.reason
        intake.candidate_case_ids = json.dumps(match.candidate_case_ids)
    intake.updated_at = now
    await db.commit()

    # New evidence is attached → re-run Rules + Evidence for the case (on its
    # own sessions, so a transient LLM failure can't break the committed attach).
    if match.status == "matched" and match.case_id:
        result = await reevaluate_case(case_id=match.case_id, claim_id=match.claim_id)
        logger.info("post-attach re-evaluation for case %s: %s", match.case_id, result)


_PROCESSORS = {
    "835": _process_835,
    "837": _process_837,
    "medical": _process_medical,
    "claim_pdf": _process_claim_pdf,
}


# ── Routes ─────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=IntakeFileOut, status_code=201)
async def upload_intake(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    app: str = Form(...),
    category: str = Form(...),
    user: OpaUser = Depends(require_role("admin", "intake")),
    db: AsyncSession = Depends(get_db),
) -> IntakeFileOut:
    if (app, category) not in _VALID_COMBOS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid app/category combination: {app}/{category}",
        )
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    if category in ("medical", "claim_pdf") and not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="A PDF file is required for this folder")

    # Store the file once (staging). The durable Document row, when created,
    # points back at this same path.
    original = safe_filename(file.filename or "upload.bin")
    stored_name = f"{category}_{uuid.uuid4().hex[:8]}_{original}"
    INTAKE_DIR.mkdir(parents=True, exist_ok=True)
    dest = INTAKE_DIR / stored_name
    dest.write_bytes(raw)
    now = datetime.utcnow().isoformat()

    intake = IntakeFile(
        intake_id=str(uuid.uuid4()),
        app=app,
        category=category,
        filename=stored_name,
        file_path=str(dest),
        file_size_kb=max(1, len(raw) // 1024),
        uploaded_at=now,
        uploaded_by_user_id=user.user_id,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    db.add(intake)

    # Process immediately (all in one transaction).
    try:
        await _PROCESSORS[category](db, intake, raw)
    except Exception as e:
        logger.exception("Intake processing failed for %s: %s", intake.intake_id, e)
        intake.status = "error"
        intake.message = f"Processing error: {e}"
        intake.updated_at = datetime.utcnow().isoformat()

    # Commit everything together
    await db.commit()
    return await _to_out(db, intake)


@router.get("", response_model=List[IntakeFileOut])
async def list_intake(
    app: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> List[IntakeFileOut]:
    stmt = select(IntakeFile)
    if app:
        stmt = stmt.where(IntakeFile.app == app)
    if category:
        stmt = stmt.where(IntakeFile.category == category)
    if status:
        stmt = stmt.where(IntakeFile.status == status)
    stmt = stmt.order_by(IntakeFile.uploaded_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [await _to_out(db, r) for r in rows]


async def _candidates_for(db: AsyncSession, case_ids: List[str]) -> List[CandidateCaseOut]:
    if not case_ids:
        return []
    rows = (await db.execute(
        select(OpaCase, Claim, Member)
        .join(Claim, OpaCase.claim_id == Claim.claim_id)
        .join(Member, OpaCase.member_id == Member.member_id)
        .where(OpaCase.case_id.in_(case_ids))
    )).all()
    out: List[CandidateCaseOut] = []
    for case, claim, member in rows:
        out.append(CandidateCaseOut(
            case_id=case.case_id,
            case_number=case.case_number,
            member_name=f"{member.first_name} {member.last_name}" if member else None,
            service_from_date=claim.service_from_date,
            service_to_date=claim.service_to_date,
            priority=case.priority,
            status=case.status,
            total_overpayment_amount=case.total_overpayment_amount,
        ))
    return out


@router.get("/unmatched", response_model=List[UnmatchedOut])
async def list_unmatched(db: AsyncSession = Depends(get_db)) -> List[UnmatchedOut]:
    rows = (await db.execute(
        select(IntakeFile)
        .where(IntakeFile.status == "unmatched")
        .order_by(IntakeFile.uploaded_at.desc())
    )).scalars().all()
    out: List[UnmatchedOut] = []
    for r in rows:
        base = await _to_out(db, r)
        candidates = await _candidates_for(db, _json_list(r.candidate_case_ids))
        out.append(UnmatchedOut(**base.model_dump(), candidates=candidates))
    return out


@router.post("/{intake_id}/resolve", response_model=IntakeFileOut)
async def resolve_intake(
    intake_id: str,
    payload: ResolveRequest,
    user: OpaUser = Depends(require_role("admin", "intake")),
    db: AsyncSession = Depends(get_db),
) -> IntakeFileOut:
    intake = (await db.execute(
        select(IntakeFile).where(IntakeFile.intake_id == intake_id)
    )).scalar_one_or_none()
    if intake is None:
        raise HTTPException(status_code=404, detail="Intake file not found")
    if intake.status != "unmatched":
        raise HTTPException(status_code=400, detail="Only unmatched documents can be resolved")

    case = (await db.execute(
        select(OpaCase).where(OpaCase.case_id == payload.case_id)
    )).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    kind = "medical_record" if intake.category == "medical" else "supporting"
    doc = await _attach_document(
        db, intake=intake, case_id=case.case_id, claim_id=case.claim_id, kind=kind,
    )
    await db.flush()

    # Manually linking an 837 → apply its Dx + claim-form metadata to the
    # awaiting claim (same enrichment as the auto-match path) before re-eval.
    if intake.category == "837" and case.claim_id:
        try:
            parsed = parse_837(Path(intake.file_path).read_text(errors="replace"))
            await enrich_claim_from_837(
                db, claim_id=case.claim_id, parsed=parsed,
                actor_user_id=user.user_id,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("837 enrichment on resolve failed for claim %s: %s", case.claim_id, e)

    # Pull stored extracted text for medical records back onto the claim corpus.
    if intake.category == "medical" and case.claim_id:
        text, pages = extract_pdf_text(Path(intake.file_path))
        if text.strip():
            doc.extracted_text = text
            doc.page_count = pages
            doc.extraction_status = "complete"
            claim = (await db.execute(
                select(Claim).where(Claim.claim_id == case.claim_id)
            )).scalar_one_or_none()
            if claim is not None:
                ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
                header = f"\n[Document: {intake.filename} | {ts} | medical_record]\n{text}\n"
                claim.extracted_text = (claim.extracted_text or "") + header

    intake.status = "linked"
    intake.message = f"Manually linked to {case.case_number}"
    intake.result_case_id = case.case_id
    intake.result_claim_id = case.claim_id
    intake.result_document_id = doc.document_id
    intake.candidate_case_ids = None
    intake.updated_at = datetime.utcnow().isoformat()
    await db.commit()

    # New evidence is attached → re-run Rules + Evidence for the case (isolated session).
    result = await reevaluate_case(case_id=case.case_id, claim_id=case.claim_id)
    logger.info("post-resolve re-evaluation for case %s: %s", case.case_id, result)

    return await _to_out(db, intake)


_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".txt": "text/plain",
    ".edi": "text/plain",
    ".x12": "text/plain",
}


@router.get("/{intake_id}/download")
async def download_intake_file(
    intake_id: str,
    inline: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Stream the raw staged intake file back. Works for every intake row —
    including UNMATCHED ones that have no durable Document yet — so the portal
    can preview what it received. `inline=true` renders in the browser (PDFs,
    images, EDI/text); the default forces a download."""
    intake = (await db.execute(
        select(IntakeFile).where(IntakeFile.intake_id == intake_id)
    )).scalar_one_or_none()
    if intake is None:
        raise HTTPException(status_code=404, detail="Intake file not found")
    p = Path(intake.file_path)
    if not p.exists():
        raise HTTPException(status_code=410, detail="File missing from disk")
    if inline:
        media_type = _MEDIA_TYPES.get(p.suffix.lower(), "application/octet-stream")
        return FileResponse(
            path=str(p), filename=intake.filename, media_type=media_type,
            content_disposition_type="inline",
        )
    return FileResponse(
        path=str(p), filename=intake.filename, media_type="application/octet-stream",
    )


@router.get("/outputs", response_model=List[OutputFileOut])
async def list_output_files(db: AsyncSession = Depends(get_db)) -> List[OutputFileOut]:
    """List system-generated output documents (recoupment letters) across all
    cases, for the Intake Portal's Output Files section."""
    rows = (await db.execute(
        select(Document, OpaCase.case_number, OpaCase.case_sequence)
        .outerjoin(OpaCase, Document.case_id == OpaCase.case_id)
        .where(Document.kind == "recoupment_letter")
        .order_by(Document.uploaded_at.desc())
    )).all()
    return [
        OutputFileOut(
            document_id=d.document_id, filename=d.filename, kind=d.kind,
            case_id=d.case_id, case_number=cn, case_sequence=cseq,
            uploaded_at=d.uploaded_at, file_size_kb=d.file_size_kb,
        )
        for d, cn, cseq in rows
    ]


@router.get("/outputs/{document_id}/download")
async def download_output_file(
    document_id: str,
    inline: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Stream an output document (recoupment letter) back — kept under the
    file-intake router so the portal's admin/intake auth is sufficient."""
    d = (await db.execute(
        select(Document).where(
            Document.document_id == document_id,
            Document.kind == "recoupment_letter",
        )
    )).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail="Output file not found")
    p = Path(d.file_path)
    if not p.exists():
        raise HTTPException(status_code=410, detail="File missing from disk")
    if inline:
        media_type = _MEDIA_TYPES.get(p.suffix.lower(), "application/octet-stream")
        return FileResponse(
            path=str(p), filename=d.filename, media_type=media_type,
            content_disposition_type="inline",
        )
    return FileResponse(
        path=str(p), filename=d.filename, media_type="application/octet-stream",
    )


@router.delete("/{intake_id}", status_code=204)
async def delete_intake(
    intake_id: str,
    user: OpaUser = Depends(require_role("admin", "intake")),
    db: AsyncSession = Depends(get_db),
) -> None:
    intake = (await db.execute(
        select(IntakeFile).where(IntakeFile.intake_id == intake_id)
    )).scalar_one_or_none()
    if intake is None:
        raise HTTPException(status_code=404, detail="Intake file not found")
    # Only remove the staged file if no durable Document points at it.
    if not intake.result_document_id:
        Path(intake.file_path).unlink(missing_ok=True)
    await db.delete(intake)
    await db.commit()
