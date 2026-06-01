"""ICD-10 / DRG evidence scanner endpoints (ClaimGuard).

Companion to `services/evidence_scanner_service.py`. Adds two routes the
analyst UI uses:

  POST /api/prepay/claims/{claim_id}/scan-evidence
       Trigger a fresh scan. Synchronous (Claude call inline) so the UI
       can show the results immediately.

  GET  /api/prepay/claims/{claim_id}/evidence-findings
       Return the latest stored findings + the code-requirement context the
       UI needs to render the panel.
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import require_app
from ..models.claims import Claim
from ..models.workflow import (
    CodeEvidenceRequirement,
    Document,
    EvidenceFinding,
)
from ..services.evidence_scanner_service import scan_claim


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/prepay/claims",
    tags=["prepay-evidence"],
    dependencies=[Depends(require_app("claimguard"))],
)


# ── response shapes ────────────────────────────────────────────────────────


class EvidenceAlternateSource(BaseModel):
    document_id: Optional[str] = None
    document_name: Optional[str] = None
    page_number: Optional[int] = None
    section_heading: Optional[str] = None
    evidence_text: Optional[str] = None


class EvidenceFindingOut(BaseModel):
    finding_id: str
    code_type: str        # 'icd10' | 'drg'
    code: str
    title: Optional[str] = None       # from requirement, if any
    description: Optional[str] = None # from requirement, if any
    result: str           # 'found' | 'partial' | 'not_found'
    confidence: Optional[str] = None  # 'high' | 'medium' | 'low'
    evidence_text: Optional[str] = None
    document_id: Optional[str] = None
    document_name: Optional[str] = None
    page_number: Optional[int] = None
    section_heading: Optional[str] = None
    additional_sources: List[EvidenceAlternateSource] = []
    gap_description: Optional[str] = None
    has_registered_requirement: bool = False
    scanned_at: str


class EvidenceFindingsResponse(BaseModel):
    claim_id: str
    findings: List[EvidenceFindingOut]
    documents_scanned: int
    last_scanned_at: Optional[str] = None


# ── helpers ────────────────────────────────────────────────────────────────


async def _resolve_claim(claim_id: str, db: AsyncSession) -> Claim:
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim


async def _build_findings_response(
    claim: Claim, db: AsyncSession,
) -> EvidenceFindingsResponse:
    # Pull findings, joined to documents + requirements for display
    rows = (await db.execute(
        select(EvidenceFinding)
        .where(EvidenceFinding.claim_id == claim.claim_id)
        .order_by(EvidenceFinding.code_type, EvidenceFinding.code)
    )).scalars().all()

    doc_ids = [r.document_id for r in rows if r.document_id]
    docs_index: dict[str, Document] = {}
    if doc_ids:
        docs = (await db.execute(
            select(Document).where(Document.document_id.in_(doc_ids))
        )).scalars().all()
        docs_index = {d.document_id: d for d in docs}

    req_ids = [r.requirement_id for r in rows if r.requirement_id]
    reqs_index: dict[str, CodeEvidenceRequirement] = {}
    if req_ids:
        reqs = (await db.execute(
            select(CodeEvidenceRequirement).where(
                CodeEvidenceRequirement.requirement_id.in_(req_ids)
            )
        )).scalars().all()
        reqs_index = {r.requirement_id: r for r in reqs}

    out: List[EvidenceFindingOut] = []
    last_ts: Optional[str] = None
    for r in rows:
        req = reqs_index.get(r.requirement_id) if r.requirement_id else None
        doc = docs_index.get(r.document_id) if r.document_id else None
        try:
            alts_raw = json.loads(r.additional_sources or "[]")
        except Exception:
            alts_raw = []
        alts: List[EvidenceAlternateSource] = []
        for a in alts_raw if isinstance(alts_raw, list) else []:
            if not isinstance(a, dict):
                continue
            alts.append(EvidenceAlternateSource(
                document_id=a.get("document_id"),
                document_name=a.get("document_name"),
                page_number=a.get("page_number"),
                section_heading=a.get("section_heading"),
                evidence_text=a.get("evidence_text"),
            ))
        out.append(EvidenceFindingOut(
            finding_id=r.finding_id,
            code_type=r.code_type,
            code=r.code,
            title=req.title if req else None,
            description=req.requirement_description if req else None,
            result=r.result,
            confidence=r.confidence,
            evidence_text=r.evidence_text,
            document_id=r.document_id,
            document_name=doc.filename if doc else None,
            page_number=r.page_number,
            section_heading=r.section_heading,
            additional_sources=alts,
            gap_description=r.gap_description,
            has_registered_requirement=req is not None,
            scanned_at=r.scanned_at,
        ))
        if last_ts is None or (r.scanned_at and r.scanned_at > last_ts):
            last_ts = r.scanned_at

    # documents_scanned reports the count of distinct medical-record-style
    # docs whose text was available at scan time.
    docs_rows = (await db.execute(
        select(Document)
        .where(Document.claim_id == claim.claim_id)
        .where(Document.kind.in_(("supporting", "medical_record")))
    )).scalars().all()
    docs_with_text = sum(1 for d in docs_rows if (d.extracted_text or "").strip())

    return EvidenceFindingsResponse(
        claim_id=claim.claim_id,
        findings=out,
        documents_scanned=docs_with_text,
        last_scanned_at=last_ts,
    )


# ── routes ─────────────────────────────────────────────────────────────────


@router.post("/{claim_id}/scan-evidence", response_model=EvidenceFindingsResponse)
async def trigger_scan(
    claim_id: str,
    db: AsyncSession = Depends(get_db),
) -> EvidenceFindingsResponse:
    """Run a fresh scan against this claim's attached medical records.
    Synchronous so the UI gets results back in one round-trip; expect a
    few seconds of latency on first run while Claude responds."""
    claim = await _resolve_claim(claim_id, db)
    try:
        await scan_claim(claim, db)
    except RuntimeError as e:
        # Missing API key or SDK — surface as 503 so the UI shows a clear
        # "service unavailable" rather than a generic 500.
        raise HTTPException(status_code=503, detail=str(e))
    await db.commit()
    return await _build_findings_response(claim, db)


@router.get("/{claim_id}/evidence-findings", response_model=EvidenceFindingsResponse)
async def list_findings(
    claim_id: str,
    db: AsyncSession = Depends(get_db),
) -> EvidenceFindingsResponse:
    """Latest stored evidence findings for the claim. Empty list when never
    scanned — the UI can use that to decide whether to auto-trigger."""
    claim = await _resolve_claim(claim_id, db)
    return await _build_findings_response(claim, db)
