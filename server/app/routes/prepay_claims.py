"""Pre-pay claim endpoints — ported from ClaimGuard's routers/claims.py.

Endpoints under /api/prepay/claims:
  POST   /from-pdf          Upload + extract + create + auto-analyze
  GET    /                  List pre-pay claims
  GET    /{claim_id}        Detail (with lazy auto-analyze on first visit)
  POST   /{claim_id}/analyze     Re-run AI audit
  POST   /{claim_id}/recheck     Append recheck note + re-analyze
  POST   /{claim_id}/summary     Generate (or refresh) LLM summary
  POST   /{claim_id}/code-descriptions  Generate ICD/CPT descriptions
"""
from __future__ import annotations

import json
import logging
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.claims import Claim, ClaimLine
from ..models.reference import Member, ProviderOrg
from ..models.workflow import (
    AuditLog, CaseFinding, CaseNote, Document, Finding,
    LikelihoodScore, OpaCase, RuntimeConfig,
)
from ..schemas.prepay_schemas import (
    AIFindingOut,
    AuditLogOut,
    CodeDescriptionsRequest,
    CommentCreate,
    CommentOut,
    DocumentOut,
    PrepayClaimDetail,
    PrepayClaimOut,
    ReanalyzeIn,
    RecheckIn,
    StatusUpdate,
    SummaryRequest,
)
from ..services import ai_service, export_service
from ..services.pdf_extraction_service import extract_text as extract_pdf_text
from ..services.prepay_intake_service import (
    IntakeValidationError,
    ingest_extracted_claim,
)


class ManualClaimCreate(BaseModel):
    """Body for manual (non-PDF) pre-pay claim creation. Patient + provider
    must still resolve to existing members/providers (the reference-data-
    first rule applies)."""
    type: Optional[str] = "CMS-1500"           # CMS-1500 | UB-04
    claim_form: Optional[str] = None            # Inpatient | Outpatient (care_setting)
    drg: Optional[str] = None
    cpts: List[str] = []
    icd10: List[str] = []
    provider: str
    patient: str
    dob: Optional[str] = None
    dos: str
    billed_amount: float = 0.0
    specialty: Optional[str] = "Other"
    description: Optional[str] = None
    icn: Optional[str] = None
    user_id: Optional[str] = None


class AssignBody(BaseModel):
    assigned_to: str
    user_id: Optional[str] = None


class MessageBody(BaseModel):
    subject: str = ""
    body: str = Field(default="", description="Message body")
    user_id: Optional[str] = None


class EvidenceExcerptOut(BaseModel):
    excerpt: str
    match_index: int

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/prepay/claims", tags=["prepay-claims"])


# ── Internal helpers ──────────────────────────────────────────────────────

async def _ai_enabled(db: AsyncSession) -> bool:
    res = await db.execute(
        select(RuntimeConfig).where(RuntimeConfig.key == "ai_suggestions_enabled")
    )
    row = res.scalar_one_or_none()
    if not row:
        return True  # default ON
    return row.value.lower() == "true"


async def _build_detail(db: AsyncSession, claim: Claim) -> PrepayClaimDetail:
    # Lines → cpts list + ICDs
    lines_res = await db.execute(
        select(ClaimLine).where(ClaimLine.claim_id == claim.claim_id)
    )
    lines = list(lines_res.scalars().all())
    cpts = [ln.cpt_code for ln in lines if ln.cpt_code]
    icd_set = set()
    icd10: List[str] = []
    for code in [claim.primary_icd] + [
        c for ln in lines if ln.icd_codes for c in (json.loads(ln.icd_codes) if ln.icd_codes else [])
    ]:
        if code and code not in icd_set:
            icd10.append(code)
            icd_set.add(code)

    # Member + provider names (denormalized into the response)
    member_name: Optional[str] = None
    dob: Optional[str] = None
    mem_res = await db.execute(select(Member).where(Member.member_id == claim.member_id))
    mem = mem_res.scalar_one_or_none()
    if mem:
        member_name = f"{mem.first_name} {mem.last_name}"
        dob = mem.date_of_birth

    provider_name: Optional[str] = None
    org_res = await db.execute(
        select(ProviderOrg).where(ProviderOrg.provider_org_id == claim.provider_org_id)
    )
    org = org_res.scalar_one_or_none()
    if org:
        provider_name = org.name

    # AI findings (subset of `findings` where detector_id='AI-CLAUDE-V1')
    f_res = await db.execute(
        select(Finding)
        .where(Finding.claim_id == claim.claim_id)
        .where(Finding.detector_id == ai_service.AI_DETECTOR_ID)
        .order_by(Finding.fired_at.asc())
    )
    ai_findings = [
        AIFindingOut(
            id=f.finding_id,
            severity=f.severity,
            title=f.title,
            body=f.rationale,
            created_at=f.fired_at,
        )
        for f in f_res.scalars().all()
    ]

    # Documents
    d_res = await db.execute(
        select(Document)
        .where(Document.claim_id == claim.claim_id)
        .order_by(Document.uploaded_at.desc())
    )
    documents = [
        DocumentOut(
            id=d.document_id,
            claim_id=d.claim_id,
            case_id=d.case_id,
            filename=d.filename,
            file_size_kb=d.file_size_kb,
            kind=d.kind,
            uploaded_at=d.uploaded_at,
            uploaded_by_user_id=d.uploaded_by_user_id,
        )
        for d in d_res.scalars().all()
    ]

    # Comments (case_notes via the case linked to this claim, if any)
    comments: List[CommentOut] = []
    assigned_to: Optional[str] = None
    case_res = await db.execute(
        select(OpaCase).where(OpaCase.claim_id == claim.claim_id).limit(1)
    )
    case = case_res.scalar_one_or_none()
    if case is not None:
        assigned_to = case.assigned_analyst_id
        notes_res = await db.execute(
            select(CaseNote)
            .where(CaseNote.case_id == case.case_id)
            .order_by(CaseNote.created_at.asc())
        )
        for n in notes_res.scalars().all():
            comments.append(CommentOut(
                id=n.note_id,
                claim_id=claim.claim_id,
                user_id=n.author_user_id,
                body=n.body,
                created_at=n.created_at,
            ))

    # Audit log (claim-level + any case-level for the linked case)
    a_res = await db.execute(
        select(AuditLog)
        .where(
            (AuditLog.claim_id == claim.claim_id)
            | (AuditLog.case_id == (case.case_id if case else "__none__"))
        )
        .order_by(AuditLog.created_at.desc())
    )
    audit_log = [
        AuditLogOut(
            id=a.audit_id,
            claim_id=a.claim_id,
            user_id=a.actor_user_id,
            action=(
                a.action if not (a.from_state and a.to_state)
                else f"{a.action}: {a.from_state} → {a.to_state}"
            ),
            created_at=a.created_at,
        )
        for a in a_res.scalars().all()
    ]

    # Priority for UI: derive from billed amount band if no case exists.
    priority: Optional[str] = None
    if case is not None:
        priority = case.priority
    else:
        b = float(claim.total_billed or 0)
        priority = "high" if b >= 50000 else ("medium" if b >= 10000 else "low")

    return PrepayClaimDetail(
        claim_id=claim.claim_id,
        icn=claim.icn,
        pipeline_mode=claim.pipeline_mode,
        claim_form_type=claim.claim_form_type,
        care_setting=claim.care_setting,
        drg=claim.drg,
        cpts=cpts,
        icd10=icd10,
        provider_name=provider_name,
        patient_name=member_name,
        dob=dob,
        dos=claim.service_from_date,
        billed_amount=float(claim.total_billed or 0),
        status=claim.claim_status,
        specialty=claim.specialty,
        description=claim.description,
        summary=claim.claim_summary,
        code_descriptions=(
            json.loads(claim.code_descriptions) if claim.code_descriptions else None
        ),
        extracted_text=claim.extracted_text or "",
        review_time_minutes=case.review_time_minutes if case else 0,
        assigned_to=assigned_to,
        priority=priority,
        ai_findings=ai_findings,
        documents=documents,
        comments=comments,
        audit_log=audit_log,
        created_at=claim.created_at,
        updated_at=claim.updated_at,
    )


async def _claim_audit(
    db: AsyncSession, *, claim_id: str, user_id: Optional[str], action: str,
    from_state: Optional[str] = None, to_state: Optional[str] = None,
) -> None:
    """Append a claim-level audit row (no case_id; ClaimGuard parity)."""
    db.add(AuditLog(
        audit_id=str(uuid.uuid4()),
        case_id=None,
        claim_id=claim_id,
        actor_user_id=user_id or "system",
        action=action,
        from_state=from_state,
        to_state=to_state,
        reason=None,
        meta_json="{}",
        created_at=datetime.utcnow().isoformat(),
    ))


async def _get_or_create_case_for_claim(
    db: AsyncSession, claim: Claim
) -> OpaCase:
    """Lazily ensure a case exists for a pre-pay claim. Workflow state on the
    claim itself stays the SoT for ClaimGuard parity; the case is just where
    case_notes and case-level audit live."""
    res = await db.execute(
        select(OpaCase).where(OpaCase.claim_id == claim.claim_id).limit(1)
    )
    case = res.scalar_one_or_none()
    if case is not None:
        return case
    now = datetime.utcnow().isoformat()
    next_seq_res = await db.execute(
        select(OpaCase).order_by(OpaCase.case_sequence.desc()).limit(1)
    )
    last = next_seq_res.scalar_one_or_none()
    next_seq = (last.case_sequence + 1) if last else 1
    case = OpaCase(
        case_id=str(uuid.uuid4()),
        case_number=f"PREPAY-CASE-{next_seq:06d}",
        case_sequence=next_seq,
        claim_id=claim.claim_id,
        case_group_id=None,
        primary_detector_id=ai_service.AI_DETECTOR_ID,
        lob=claim.lob,
        provider_org_id=claim.provider_org_id,
        member_id=claim.member_id,
        assigned_analyst_id=None,
        status="new",
        is_active=True,
        priority="MEDIUM",
        priority_score=50.0,
        total_overpayment_amount=None,
        review_time_minutes=0,
        recommended_recovery_method="prepay_review",
        identified_date=now[:10],
        deadline_date=now[:10],
        deadline_breached=False,
        lookback_window_start=now[:10],
        provider_response_due_date=None,
        is_sensitive_provider=False,
        requires_supervisor_approval=False,
        evidence_bundle="{}",
        case_json="{}",
        decision_metadata=None,
        created_at=now,
        updated_at=now,
    )
    db.add(case)
    await db.flush()
    return case


# ── Routes ────────────────────────────────────────────────────────────────

@router.post("/from-pdf", response_model=PrepayClaimDetail, status_code=201)
async def create_from_pdf(
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    auto_analyze: bool = Form(True),
    db: AsyncSession = Depends(get_db),
) -> PrepayClaimDetail:
    """Ingest a CMS-1500 or UB-04 PDF. Extracts structured fields with Claude,
    validates member + provider against reference data, creates the claim
    with pipeline_mode='pre_pay', attaches the PDF as kind='claim_form', and
    (by default) runs the AI audit."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF required")

    # Extract text — write to a temp file because pdfplumber needs a path.
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = Path(tmp.name)
    try:
        pdf_text, _pages = extract_pdf_text(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    if not pdf_text.strip():
        raise HTTPException(
            status_code=422,
            detail="PDF contains no extractable text (likely an image-only scan).",
        )

    # LLM extraction
    try:
        extracted = await ai_service.extract_claim_from_text(pdf_text)
    except Exception as e:
        logger.exception("Extraction failed")
        raise HTTPException(status_code=502, detail=f"Extraction failed: {e}")

    # Validate + persist (raises IntakeValidationError on unknown member/provider)
    try:
        claim_id = await ingest_extracted_claim(
            db,
            extracted=extracted,
            pdf_bytes=raw,
            pdf_filename=file.filename or "claim.pdf",
            uploaded_by_user_id=user_id,
        )
    except IntakeValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    await _claim_audit(db, claim_id=claim_id, user_id=user_id,
                       action=f"Claim ingested from PDF: {file.filename}")
    await db.commit()

    if auto_analyze:
        try:
            await ai_service.analyze_claim(claim_id, db)
        except Exception as e:
            logger.exception("Auto-analyze failed for %s: %s", claim_id, e)

    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one()
    return await _build_detail(db, claim)


@router.post("", response_model=PrepayClaimDetail, status_code=201)
async def create_claim_manual(
    body: ManualClaimCreate,
    db: AsyncSession = Depends(get_db),
) -> PrepayClaimDetail:
    """Manual (no-PDF) pre-pay claim creation. Patient + provider must already
    exist as reference data (members + provider_orgs)."""
    extracted = {
        "type": body.type,
        "claim_form": body.claim_form,
        "drg": body.drg,
        "cpts": body.cpts,
        "icd10": body.icd10,
        "provider": body.provider,
        "patient": body.patient,
        "dob": body.dob,
        "dos": body.dos,
        "billed_amount": body.billed_amount,
        "specialty": body.specialty,
        "description": body.description,
    }
    try:
        claim_id = await ingest_extracted_claim(
            db,
            extracted=extracted,
            pdf_bytes=None,
            pdf_filename=None,
            uploaded_by_user_id=body.user_id,
            icn=body.icn,
        )
    except IntakeValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    await _claim_audit(
        db, claim_id=claim_id, user_id=body.user_id,
        action="Claim created via manual intake",
    )
    await db.commit()

    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one()
    return await _build_detail(db, claim)


@router.get("", response_model=List[PrepayClaimOut])
async def list_prepay_claims(
    status: Optional[str] = None,
    specialty: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> List[PrepayClaimOut]:
    stmt = select(Claim).where(Claim.pipeline_mode == "pre_pay")
    if status:
        stmt = stmt.where(Claim.claim_status == status)
    if specialty:
        stmt = stmt.where(Claim.specialty == specialty)
    stmt = stmt.order_by(Claim.created_at.desc())
    res = await db.execute(stmt)
    claims = list(res.scalars().all())

    # Build cheap per-claim outs (no detail joins).
    out: List[PrepayClaimOut] = []
    for c in claims:
        # Pull lines for CPTs
        l_res = await db.execute(select(ClaimLine).where(ClaimLine.claim_id == c.claim_id))
        lines = list(l_res.scalars().all())
        cpts = [ln.cpt_code for ln in lines if ln.cpt_code]
        # Member/provider names
        m = (await db.execute(select(Member).where(Member.member_id == c.member_id))).scalar_one_or_none()
        o = (await db.execute(select(ProviderOrg).where(ProviderOrg.provider_org_id == c.provider_org_id))).scalar_one_or_none()

        out.append(PrepayClaimOut(
            claim_id=c.claim_id,
            icn=c.icn,
            pipeline_mode=c.pipeline_mode,
            claim_form_type=c.claim_form_type,
            care_setting=c.care_setting,
            drg=c.drg,
            cpts=cpts,
            icd10=[c.primary_icd] if c.primary_icd else [],
            provider_name=o.name if o else None,
            patient_name=f"{m.first_name} {m.last_name}" if m else None,
            dob=m.date_of_birth if m else None,
            dos=c.service_from_date,
            billed_amount=float(c.total_billed or 0),
            status=c.claim_status,
            specialty=c.specialty,
            description=c.description,
            summary=c.claim_summary,
            code_descriptions=(json.loads(c.code_descriptions) if c.code_descriptions else None),
            created_at=c.created_at,
            updated_at=c.updated_at,
        ))
    return out


@router.get("/{claim_id}", response_model=PrepayClaimDetail)
async def get_prepay_claim(
    claim_id: str,
    db: AsyncSession = Depends(get_db),
) -> PrepayClaimDetail:
    res = await db.execute(select(Claim).where(Claim.claim_id == claim_id))
    claim = res.scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    # ClaimGuard parity: lazy auto-analyze on first detail visit if no AI
    # findings exist and the ai_suggestions_enabled flag is on.
    f_res = await db.execute(
        select(Finding)
        .where(Finding.claim_id == claim_id)
        .where(Finding.detector_id == ai_service.AI_DETECTOR_ID)
        .limit(1)
    )
    if f_res.scalar_one_or_none() is None and await _ai_enabled(db):
        try:
            await ai_service.analyze_claim(claim_id, db)
        except Exception as e:
            logger.exception("Lazy auto-analyze failed for %s: %s", claim_id, e)

    return await _build_detail(db, claim)


@router.post("/{claim_id}/analyze", response_model=PrepayClaimDetail)
async def reanalyze(
    claim_id: str,
    payload: ReanalyzeIn,
    db: AsyncSession = Depends(get_db),
) -> PrepayClaimDetail:
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    await _claim_audit(db, claim_id=claim_id, user_id=payload.user_id,
                       action="AI re-analysis requested manually")
    await db.commit()
    try:
        await ai_service.analyze_claim(claim_id, db)
    except Exception as e:
        logger.exception("AI re-analysis failed for %s: %s", claim_id, e)
    return await _build_detail(db, claim)


@router.post("/{claim_id}/recheck", response_model=PrepayClaimDetail)
async def recheck(
    claim_id: str,
    payload: RecheckIn,
    db: AsyncSession = Depends(get_db),
) -> PrepayClaimDetail:
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    header = f"[Recheck note | {ts}]\n{payload.note}\n\n"
    claim.extracted_text = (claim.extracted_text or "") + header
    await _claim_audit(db, claim_id=claim_id, user_id=payload.user_id,
                       action="Recheck triggered; AI re-analysis requested")
    await db.commit()
    try:
        await ai_service.analyze_claim(claim_id, db)
    except Exception as e:
        logger.exception("AI recheck failed for %s: %s", claim_id, e)
    return await _build_detail(db, claim)


@router.post("/{claim_id}/summary", response_model=PrepayClaimDetail)
async def claim_summary(
    claim_id: str,
    payload: SummaryRequest = SummaryRequest(),
    db: AsyncSession = Depends(get_db),
) -> PrepayClaimDetail:
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.claim_summary and not payload.force:
        return await _build_detail(db, claim)
    try:
        text = await ai_service.generate_claim_summary(claim_id, db)
    except Exception as e:
        logger.exception("Summary generation failed for %s: %s", claim_id, e)
        raise HTTPException(status_code=502, detail=f"Summary failed: {e}")
    claim.claim_summary = text
    await db.commit()
    return await _build_detail(db, claim)


@router.patch("/{claim_id}/status", response_model=PrepayClaimDetail)
async def update_status(
    claim_id: str,
    payload: StatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> PrepayClaimDetail:
    """Update claim_status. Cumulative review_time_minutes (monotonic) lives on
    the linked case, lazily created on first workflow action."""
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    old = claim.claim_status
    claim.claim_status = payload.status
    claim.updated_at = datetime.utcnow().isoformat()
    await _claim_audit(
        db, claim_id=claim_id, user_id=payload.user_id,
        action="Status changed", from_state=old, to_state=payload.status,
    )
    if payload.review_time_minutes is not None and payload.review_time_minutes > 0:
        case = await _get_or_create_case_for_claim(db, claim)
        case.review_time_minutes = max(
            case.review_time_minutes or 0, payload.review_time_minutes
        )
    await db.commit()
    return await _build_detail(db, claim)


@router.post("/{claim_id}/comments", response_model=CommentOut, status_code=201)
async def add_comment(
    claim_id: str,
    payload: CommentCreate,
    db: AsyncSession = Depends(get_db),
) -> CommentOut:
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    case = await _get_or_create_case_for_claim(db, claim)
    now = datetime.utcnow().isoformat()
    note = CaseNote(
        note_id=str(uuid.uuid4()),
        case_id=case.case_id,
        author_user_id=payload.user_id,
        body=payload.body,
        created_at=now,
    )
    db.add(note)
    await _claim_audit(
        db, claim_id=claim_id, user_id=payload.user_id, action="Comment added"
    )
    await db.commit()
    return CommentOut(
        id=note.note_id,
        claim_id=claim_id,
        user_id=note.author_user_id,
        body=note.body,
        created_at=note.created_at,
    )


@router.get("/{claim_id}/comments", response_model=List[CommentOut])
async def list_comments(
    claim_id: str, db: AsyncSession = Depends(get_db),
) -> List[CommentOut]:
    case_res = await db.execute(
        select(OpaCase).where(OpaCase.claim_id == claim_id).limit(1)
    )
    case = case_res.scalar_one_or_none()
    if case is None:
        return []
    notes_res = await db.execute(
        select(CaseNote).where(CaseNote.case_id == case.case_id)
        .order_by(CaseNote.created_at.asc())
    )
    return [
        CommentOut(
            id=n.note_id, claim_id=claim_id, user_id=n.author_user_id,
            body=n.body, created_at=n.created_at,
        )
        for n in notes_res.scalars().all()
    ]


@router.post("/{claim_id}/code-descriptions", response_model=PrepayClaimDetail)
async def claim_code_descriptions(
    claim_id: str,
    payload: CodeDescriptionsRequest = CodeDescriptionsRequest(),
    db: AsyncSession = Depends(get_db),
) -> PrepayClaimDetail:
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.code_descriptions and not payload.force:
        return await _build_detail(db, claim)

    # Re-assemble codes from lines (current source of truth for CPTs/ICDs).
    lines_res = await db.execute(select(ClaimLine).where(ClaimLine.claim_id == claim_id))
    lines = list(lines_res.scalars().all())
    cpts = [ln.cpt_code for ln in lines if ln.cpt_code]
    icd_set = set()
    icd10: List[str] = []
    for code in [claim.primary_icd] + [
        c for ln in lines if ln.icd_codes for c in (json.loads(ln.icd_codes) if ln.icd_codes else [])
    ]:
        if code and code not in icd_set:
            icd10.append(code)
            icd_set.add(code)

    try:
        mapping = await ai_service.generate_code_descriptions(icd10, cpts)
    except Exception as e:
        logger.exception("Code-description generation failed for %s: %s", claim_id, e)
        raise HTTPException(status_code=502, detail=f"Description lookup failed: {e}")
    claim.code_descriptions = json.dumps(mapping)
    await db.commit()
    return await _build_detail(db, claim)


# ── Export / reassign / message / evidence ───────────────────────────────

async def _export_context(db: AsyncSession, claim: Claim) -> dict:
    """Assemble the dict consumed by export_service.generate_*."""
    detail = await _build_detail(db, claim)
    return {
        "claim_id": claim.claim_id,
        "icn": claim.icn,
        "claim_form_type": detail.claim_form_type,
        "care_setting": detail.care_setting,
        "drg": detail.drg,
        "specialty": detail.specialty,
        "description": detail.description,
        "status": detail.status,
        "priority": detail.priority,
        "patient": detail.patient_name,
        "dob": detail.dob,
        "provider": detail.provider_name,
        "dos": detail.dos,
        "billed_amount": detail.billed_amount,
        "cpts": detail.cpts,
        "icd10": detail.icd10,
    }


@router.patch("/{claim_id}/assign", response_model=PrepayClaimDetail)
async def reassign(
    claim_id: str,
    body: AssignBody,
    db: AsyncSession = Depends(get_db),
) -> PrepayClaimDetail:
    """Reassign a pre-pay claim to a different analyst. Assignment lives on
    the lazily-created opa_case (opa_cases.assigned_analyst_id)."""
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    from ..models.workflow import OpaUser
    target = (await db.execute(
        select(OpaUser).where(OpaUser.user_id == body.assigned_to)
    )).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=400, detail="Target user not found")

    case = await _get_or_create_case_for_claim(db, claim)
    old_id = case.assigned_analyst_id
    case.assigned_analyst_id = body.assigned_to
    case.updated_at = datetime.utcnow().isoformat()

    old_label = "Unassigned"
    if old_id:
        old_user = (await db.execute(
            select(OpaUser).where(OpaUser.user_id == old_id)
        )).scalar_one_or_none()
        old_label = old_user.full_name if old_user else f"user#{old_id[:8]}"
    new_label = target.full_name

    await _claim_audit(
        db, claim_id=claim_id, user_id=body.user_id,
        action=f"Reassigned from {old_label} to {new_label}",
    )
    await db.commit()
    return await _build_detail(db, claim)


@router.post("/{claim_id}/messages", response_model=PrepayClaimDetail)
async def message_provider(
    claim_id: str,
    body: MessageBody,
    db: AsyncSession = Depends(get_db),
) -> PrepayClaimDetail:
    """Record an outbound provider message. Currently just an audit-log entry —
    matches ClaimGuard's behavior (no transport, only the trail)."""
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    subject = (body.subject or "").strip() or "Provider message"
    await _claim_audit(
        db, claim_id=claim_id, user_id=body.user_id,
        action=f"Provider message sent: {subject}",
    )
    await db.commit()
    return await _build_detail(db, claim)


@router.get("/{claim_id}/evidence", response_model=List[EvidenceExcerptOut])
async def evidence_search(
    claim_id: str,
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
) -> List[EvidenceExcerptOut]:
    """Search the appended AI evidence corpus for a substring and return up
    to 3 surrounding excerpts (matches ClaimGuard's UX)."""
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    text = claim.extracted_text or ""
    if not text:
        return []
    needle = q.lower()
    haystack = text.lower()
    out: List[EvidenceExcerptOut] = []
    start = 0
    while len(out) < 3:
        idx = haystack.find(needle, start)
        if idx == -1:
            break
        lo = max(0, idx - 150)
        hi = min(len(text), idx + len(q) + 150)
        out.append(EvidenceExcerptOut(excerpt=text[lo:hi], match_index=idx))
        start = idx + len(q)
    return out


@router.get("/{claim_id}/export/denial")
async def export_denial(
    claim_id: str,
    user_id: str = Query(...),
    reason: str = Query(
        "Claim denied based on payment integrity review findings. "
        "See attached AI findings for the specific coding and medical necessity "
        "issues that supported this determination."
    ),
    db: AsyncSession = Depends(get_db),
):
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    f_res = await db.execute(
        select(Finding)
        .where(Finding.claim_id == claim_id)
        .where(Finding.detector_id == ai_service.AI_DETECTOR_ID)
        .order_by(Finding.fired_at.asc())
    )
    findings = [
        {"severity": f.severity, "title": f.title, "body": f.rationale}
        for f in f_res.scalars().all()
    ]
    ctx = await _export_context(db, claim)
    zip_bytes = export_service.generate_denial_zip(ctx, findings, reason)
    await _claim_audit(
        db, claim_id=claim_id, user_id=user_id, action="Denial package exported",
    )
    await db.commit()
    fname = f"{claim.icn or claim.claim_id[:8]}-denial.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/{claim_id}/export/approval")
async def export_approval(
    claim_id: str,
    user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    f_res = await db.execute(
        select(Finding)
        .where(Finding.claim_id == claim_id)
        .where(Finding.detector_id == ai_service.AI_DETECTOR_ID)
        .order_by(Finding.fired_at.asc())
    )
    findings = [
        {"severity": f.severity, "title": f.title, "body": f.rationale}
        for f in f_res.scalars().all()
    ]
    d_res = await db.execute(
        select(Document).where(Document.claim_id == claim_id)
    )
    documents = [
        {"filename": d.filename, "file_path": d.file_path}
        for d in d_res.scalars().all()
    ]
    ctx = await _export_context(db, claim)
    zip_bytes = export_service.generate_approval_zip(ctx, findings, documents)
    await _claim_audit(
        db, claim_id=claim_id, user_id=user_id, action="Approval package exported",
    )
    await db.commit()
    fname = f"{claim.icn or claim.claim_id[:8]}-approval.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
