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
from ..middleware.auth import require_app
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.claims import Claim, ClaimLine
from ..models.reference import Member, ProviderOrg
from ..models.workflow import (
    AuditLog, CaseFinding, CaseNote, Document, Finding,
    LikelihoodScore, OpaCase, PrepayFindingDecision, RuntimeConfig,
)
from ..schemas.prepay_schemas import (
    AIFindingOut,
    AuditLogOut,
    ClaimLineOut,
    CodeDescriptionsRequest,
    CommentCreate,
    CommentOut,
    DocumentOut,
    FindingDecisionIn,
    FindingDecisionOut,
    FindingsLetterIn,
    FindingsLetterOut,
    PrepayClaimDetail,
    PrepayClaimOut,
    ReanalyzeIn,
    RecheckIn,
    StatusUpdate,
    SummaryRequest,
)
from ..schemas.siu_schemas import EscalateCaseIn
from ..services import ai_service, export_service
from ..services.pdf_extraction_service import extract_text as extract_pdf_text
from ..services.siu_service import SIUService
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


class SendToSiuBody(BaseModel):
    """Refer a pre-pay claim to the Special Investigations Unit. Resolves the
    claim's case and escalates it via SIUService so it surfaces in the SIU app."""
    reason: str = Field(min_length=1, description="Why this claim is being referred to SIU")
    investigation_type: str = "FRAUD_PATTERN"
    user_id: Optional[str] = None


class EvidenceExcerptOut(BaseModel):
    excerpt: str
    match_index: int

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/prepay/claims", tags=["prepay-claims"], dependencies=[Depends(require_app("claimguard"))])


# ── Internal helpers ──────────────────────────────────────────────────────

_SEVERITY_MAP = {"HIGH": "critical", "MEDIUM": "warning", "LOW": "ok"}


def _normalize_severity(raw: str) -> str:
    """Detectors store HIGH/MEDIUM/LOW; the UI expects critical/warning/ok."""
    return _SEVERITY_MAP.get(raw.upper(), raw.lower())


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

    # All findings for this claim — detector rules (DET-*/STR-*/CHG-*),
    # FWA signals, and any legacy CG-BASIC-V1 entries. The UI uses
    # fwa_indicator + fwa_rule_code to render FWA-XX badges.
    f_res = await db.execute(
        select(Finding)
        .where(Finding.claim_id == claim.claim_id)
        .order_by(Finding.fired_at.asc())
    )
    finding_rows = list(f_res.scalars().all())

    # Specialist Accept/Reject decisions for those findings.
    decisions_by_finding: dict[str, PrepayFindingDecision] = {}
    if finding_rows:
        dec_res = await db.execute(
            select(PrepayFindingDecision).where(
                PrepayFindingDecision.finding_id.in_(
                    [f.finding_id for f in finding_rows]
                )
            )
        )
        decisions_by_finding = {
            d.finding_id: d for d in dec_res.scalars().all()
        }

    ai_findings = [
        AIFindingOut(
            id=f.finding_id,
            severity=_normalize_severity(f.severity),
            title=f.title,
            body=f.rationale,
            issue_summary=f.issue_summary,
            suggestion=f.suggestion,
            created_at=f.fired_at,
            detector_id=f.detector_id,
            fwa_indicator=bool(f.fwa_indicator),
            fwa_rule_code=f.fwa_rule_code,
            decision=(
                FindingDecisionOut(
                    status=d.status,
                    comment=d.comment,
                    decided_by_user_id=d.decided_by_user_id,
                    decided_at=d.decided_at,
                )
                if (d := decisions_by_finding.get(f.finding_id))
                else None
            ),
        )
        for f in finding_rows
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

    claim_lines_out = [
        ClaimLineOut(
            id=ln.claim_line_id,
            line_number=ln.line_number,
            revenue_code=ln.revenue_code,
            cpt_code=ln.cpt_code,
            modifier_1=ln.modifier_1,
            modifier_2=ln.modifier_2,
            units_billed=ln.units_billed,
            billed_amount=ln.billed_amount,
            icd_codes=json.loads(ln.icd_codes) if ln.icd_codes else [],
        )
        for ln in sorted(lines, key=lambda l: l.line_number)
    ]

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
        case_number=case.case_number if case else None,
        case_status=case.status if case else None,
        lines=claim_lines_out,
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


PREPAY_CASE_STATUSES = {"new", "in_process", "awaiting_info", "escalated", "closed"}


async def _get_or_create_case_for_claim(
    db: AsyncSession, claim: Claim
) -> OpaCase:
    """Ensure a case exists for a claim. Called eagerly at intake so every
    claim enters the system with a case; also called as a safety net on older
    rows that predate eager creation."""
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
    # Unified platform case number: pre-pay cases share the OPA-YYYY-NNNNN
    # scheme with post-pay (case_sequence is a single monotonic counter across
    # both pipelines), so referrals surface consistently in the SIU app.
    case = OpaCase(
        case_id=str(uuid.uuid4()),
        case_number=f"OPA-{datetime.utcnow().year}-{next_seq:05d}",
        case_sequence=next_seq,
        claim_id=claim.claim_id,
        case_group_id=None,
        primary_detector_id=ai_service.AI_DETECTOR_ID,
        pipeline_mode=claim.pipeline_mode,
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
        raise HTTPException(
            status_code=502,
            detail="Couldn't read the claim details from this document. "
                   "Please try again or upload a different file.",
        )

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
        # Open the case immediately so findings have a case to link to.
        try:
            from ..services.detector_service import DetectorService
            claim_for_dets = (await db.execute(
                select(Claim).where(Claim.claim_id == claim_id)
            )).scalar_one()
            case = await _get_or_create_case_for_claim(db, claim_for_dets)
            await db.flush()
            # Run all configured detector rules (DET-*/FWA-*). DetectorService
            # filters to pre_pay-applicable rules automatically.
            await DetectorService(db).run_for_case(
                case.case_sequence, pipeline_mode="pre_pay",
            )
            # run_for_case commits internally.
        except Exception as e:
            logger.exception("Auto-detector pass failed for %s: %s", claim_id, e)
        # LLM-assisted FWA — FWA-04 upcoding + FWA-07 diagnosis inflation.
        # Fails soft on missing API key so dev environments without
        # ANTHROPIC_API_KEY don't break intake.
        try:
            from ..services import fwa_service
            await fwa_service.run(claim_id, db)
            await db.commit()
        except Exception as e:
            logger.exception("Auto-FWA-LLM failed for %s: %s", claim_id, e)
        # Initial code-evidence scan runs against whatever PDFs are attached
        # at intake time (the claim form itself when no medical records yet).
        # Failures are non-fatal — the analyst can re-scan from the UI.
        try:
            from ..services.evidence_scanner_service import scan_claim
            claim_for_scan = (await db.execute(
                select(Claim).where(Claim.claim_id == claim_id)
            )).scalar_one()
            await scan_claim(claim_for_scan, db)
            await db.commit()
        except Exception as e:
            logger.exception("Auto-scan-evidence failed for %s: %s", claim_id, e)

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

    # Open a case immediately and run detectors so findings are available
    # on first view — no lazy analysis needed.
    try:
        from ..services.detector_service import DetectorService
        case = await _get_or_create_case_for_claim(db, claim)
        await db.flush()
        await DetectorService(db).run_for_case(
            case.case_sequence, pipeline_mode="pre_pay",
        )
    except Exception as e:
        logger.exception("Detector pass failed for manual claim %s: %s", claim_id, e)

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

    # Lazy detector run on first visit for claims that predate eager intake
    # (e.g. seeded rows). New claims created via intake endpoints already have
    # a case + findings by the time the first GET arrives.
    f_res = await db.execute(
        select(Finding).where(Finding.claim_id == claim_id).limit(1)
    )
    if f_res.scalar_one_or_none() is None:
        try:
            from ..services.detector_service import DetectorService
            case = await _get_or_create_case_for_claim(db, claim)
            await db.flush()
            await DetectorService(db).run_for_case(
                case.case_sequence, pipeline_mode="pre_pay",
            )
        except Exception as e:
            logger.exception("Lazy detector run failed for %s: %s", claim_id, e)

    return await _build_detail(db, claim)


@router.post("/{claim_id}/run-detectors", response_model=PrepayClaimDetail)
async def run_detectors(
    claim_id: str,
    payload: ReanalyzeIn,
    db: AsyncSession = Depends(get_db),
) -> PrepayClaimDetail:
    """Re-run all configured detector rules against this claim. Clears prior
    findings and replaces them with a fresh pass of the enabled DET-*/FWA-* rules."""
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    case = await _get_or_create_case_for_claim(db, claim)
    await db.flush()
    await _claim_audit(db, claim_id=claim_id, user_id=payload.user_id,
                       action="Detector rules re-run requested")
    await db.commit()

    try:
        from ..services.detector_service import DetectorService
        await DetectorService(db).run_for_case(
            case.case_sequence, pipeline_mode="pre_pay",
        )
    except Exception as e:
        logger.exception("Detector re-run failed for %s: %s", claim_id, e)
        raise HTTPException(status_code=502, detail="Rules check failed. Please try again.")

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
                       action="Recheck note appended")
    await db.commit()
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
        raise HTTPException(
            status_code=502,
            detail="Couldn't generate the claim summary right now. Please try again.",
        )
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

    # Mirror claim decision onto the case lifecycle.
    # approved/denied → close the case; siu_review → escalate it.
    case = await _get_or_create_case_for_claim(db, claim)
    if payload.review_time_minutes is not None and payload.review_time_minutes > 0:
        case.review_time_minutes = max(case.review_time_minutes or 0, payload.review_time_minutes)
    if payload.status in ("approved", "denied") and case.status != "closed":
        case.status = "closed"
        case.is_active = False
        case.updated_at = datetime.utcnow().isoformat()
    elif payload.status == "siu_review" and case.status not in ("escalated", "closed"):
        case.status = "escalated"
        case.updated_at = datetime.utcnow().isoformat()

    await db.commit()
    return await _build_detail(db, claim)


class CaseStatusUpdate(BaseModel):
    status: str   # new | in_process | awaiting_info | escalated | closed
    user_id: Optional[str] = None


@router.patch("/{claim_id}/case-status", response_model=PrepayClaimDetail)
async def update_case_status(
    claim_id: str,
    payload: CaseStatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> PrepayClaimDetail:
    """Transition the investigation case through its prepay lifecycle statuses,
    independent of the claim payment decision."""
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    if payload.status not in PREPAY_CASE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid case status. Must be one of: {sorted(PREPAY_CASE_STATUSES)}",
        )

    case = await _get_or_create_case_for_claim(db, claim)
    if case.status == "closed" and payload.status != "closed":
        raise HTTPException(status_code=400, detail="Cannot reopen a closed case")

    old = case.status
    case.status = payload.status
    case.is_active = payload.status != "closed"
    case.updated_at = datetime.utcnow().isoformat()
    db.add(AuditLog(
        audit_id=str(uuid.uuid4()),
        case_id=case.case_id,
        claim_id=claim_id,
        actor_user_id=payload.user_id or "system",
        action="CASE_STATUS_CHANGED",
        from_state=old,
        to_state=payload.status,
        reason=None,
        meta_json="{}",
        created_at=datetime.utcnow().isoformat(),
    ))
    await db.commit()
    return await _build_detail(db, claim)


@router.post("/{claim_id}/send-to-siu", response_model=PrepayClaimDetail)
async def send_to_siu(
    claim_id: str,
    payload: SendToSiuBody,
    db: AsyncSession = Depends(get_db),
) -> PrepayClaimDetail:
    """Refer a pre-pay claim to SIU. Resolves (or lazily creates) the claim's
    case and escalates it through SIUService — freezing the case, creating an
    SIU investigation, and surfacing it in the SIU app's queue. The claim's own
    status is set to 'siu_review' so the ClaimGuard UI reflects the referral."""
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    case = await _get_or_create_case_for_claim(db, claim)
    if case.siu_investigation_id:
        raise HTTPException(
            status_code=409,
            detail=f"Claim is already referred to SIU (investigation {case.siu_investigation_id}).",
        )

    # Reflect the referral on the claim itself (ClaimGuard's status SoT) before
    # escalate_case commits the transaction.
    old = claim.claim_status
    claim.claim_status = "siu_review"
    claim.updated_at = datetime.utcnow().isoformat()
    await _claim_audit(
        db, claim_id=claim_id, user_id=payload.user_id,
        action="Referred to SIU", from_state=old, to_state="siu_review",
    )

    # escalate_case freezes the case, sets status SIU_REFERRAL, creates the
    # investigation, writes the SIU_ESCALATED audit row, and commits.
    await SIUService(db).escalate_case(
        EscalateCaseIn(
            case_id=case.case_id,
            investigation_type=payload.investigation_type,
            escalation_source="analyst_referral",
            escalation_reason=payload.reason,
        ),
        actor_user_id=payload.user_id or "system",
    )
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
        raise HTTPException(
            status_code=502,
            detail="Couldn't look up the code descriptions right now. Please try again.",
        )
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


@router.put(
    "/{claim_id}/findings/{finding_id}/decision",
    response_model=PrepayClaimDetail,
)
async def set_finding_decision(
    claim_id: str,
    finding_id: str,
    payload: FindingDecisionIn,
    db: AsyncSession = Depends(get_db),
) -> PrepayClaimDetail:
    """Record the specialist's Accept/Reject decision on a single AI finding.

    status='accepted' marks the issue valid (its suggestion will be included in
    the provider correction letter). status='rejected' dismisses it, optionally
    with a comment. status='pending' clears any prior decision.
    """
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    finding = (await db.execute(
        select(Finding).where(
            Finding.finding_id == finding_id,
            Finding.claim_id == claim_id,
        )
    )).scalar_one_or_none()
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found on this claim")

    existing = (await db.execute(
        select(PrepayFindingDecision).where(
            PrepayFindingDecision.finding_id == finding_id
        )
    )).scalar_one_or_none()

    now = datetime.utcnow().isoformat()
    comment = (payload.comment or "").strip() or None

    if payload.status == "pending":
        if existing is not None:
            await db.delete(existing)
        action = "AI finding decision cleared"
    else:
        if existing is None:
            existing = PrepayFindingDecision(
                decision_id=str(uuid.uuid4()),
                finding_id=finding_id,
                claim_id=claim_id,
            )
            db.add(existing)
        existing.status = payload.status
        existing.comment = comment
        existing.decided_by_user_id = payload.user_id
        existing.decided_at = now
        verb = "accepted" if payload.status == "accepted" else "rejected"
        action = f"AI finding {verb}: {finding.title or finding.finding_id[:8]}"

    await _claim_audit(db, claim_id=claim_id, user_id=payload.user_id, action=action)
    await db.commit()
    return await _build_detail(db, claim)


def _build_findings_letter(
    detail: PrepayClaimDetail, accepted: List[AIFindingOut]
) -> str:
    """Render a provider-facing claim-correction letter from accepted findings."""
    today = datetime.utcnow().strftime("%B %d, %Y")
    amount = f"${detail.billed_amount:,.2f}"
    lines: List[str] = [
        today,
        "",
        f"RE: Claim Correction Request — Claim {detail.icn or detail.claim_id}",
        f"Patient: {detail.patient_name or 'N/A'}    "
        f"Date of Service: {detail.dos or 'N/A'}",
        f"Provider: {detail.provider_name or 'N/A'}",
        f"Claim Form: {detail.claim_form_type or 'N/A'} "
        f"({detail.care_setting or 'N/A'})    Billed Amount: {amount}",
        "",
        "Dear Billing Provider,",
        "",
        "Our pre-payment review of the claim referenced above identified the "
        "following item(s) that require your attention before the claim can be "
        "processed for payment. Please review each item, make the recommended "
        "corrections, and resubmit the corrected claim.",
        "",
    ]
    for i, f in enumerate(accepted, start=1):
        issue = (f.issue_summary or f.body or "").strip()
        suggestion = (f.suggestion or "").strip()
        lines.append(f"{i}. {f.title or 'Finding'}")
        if issue:
            lines.append(f"   Issue: {issue}")
        if suggestion:
            lines.append(f"   Recommended action: {suggestion}")
        lines.append("")

    lines.extend([
        "Please submit your corrected claim within the timeframe specified in "
        "your provider agreement. If you believe any item above was identified "
        "in error, you may respond to this notice with supporting documentation.",
        "",
        "Thank you for your prompt attention to this matter.",
        "",
        "Sincerely,",
        "ClaimGuard Payment Integrity Team",
    ])
    return "\n".join(lines)


@router.post("/{claim_id}/findings-letter", response_model=FindingsLetterOut)
async def generate_findings_letter(
    claim_id: str,
    payload: FindingsLetterIn,
    db: AsyncSession = Depends(get_db),
) -> FindingsLetterOut:
    """Compile every Accepted AI finding (issue + suggestion) into a single
    provider-facing correction letter."""
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    detail = await _build_detail(db, claim)
    accepted = [
        f for f in detail.ai_findings
        if f.decision is not None and f.decision.status == "accepted"
    ]
    if not accepted:
        raise HTTPException(
            status_code=400,
            detail="No accepted findings — accept at least one finding first.",
        )

    letter = _build_findings_letter(detail, accepted)
    await _claim_audit(
        db, claim_id=claim_id, user_id=payload.user_id,
        action=f"Provider correction letter generated ({len(accepted)} item(s))",
    )
    await db.commit()
    return FindingsLetterOut(
        letter=letter,
        accepted_count=len(accepted),
        generated_at=datetime.utcnow().isoformat(),
    )


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
