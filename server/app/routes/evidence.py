"""Evidence-validation endpoint — runs a targeted AI pass that checks each
billed CPT/ICD against the chart text attached to the claim. Pipeline-
agnostic: usable on both pre-pay (ClaimGuard) and post-pay (PayGuard) claims.

The AI findings are persisted to the unified findings table with
detector_id='AI-EVIDENCE-V1' so they can be distinguished from the general
AI audit findings (detector_id='CG-BASIC-V1') and from deterministic edits.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from ..middleware.auth import require_any_app
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.claims import Claim
from ..models.workflow import Finding
from ..services import ai_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/claims", tags=["evidence"], dependencies=[Depends(require_any_app("payguard", "claimguard", "assistant"))])


class EvidenceFindingOut(BaseModel):
    id: str
    claim_id: str
    code: Optional[str] = None           # the CPT/ICD this finding validates
    severity: str                          # critical | warning | ok
    title: Optional[str] = None
    body: str
    created_at: str


class ValidateEvidenceResponse(BaseModel):
    claim_id: str
    chart_text_chars: int                  # how much chart text we ran against
    findings: List[EvidenceFindingOut]


def _f_to_out(f: Finding) -> EvidenceFindingOut:
    import json as _json
    code = None
    try:
        ev = _json.loads(f.evidence or "{}")
        code = ev.get("code")
    except Exception:
        pass
    return EvidenceFindingOut(
        id=f.finding_id,
        claim_id=f.claim_id,
        code=code,
        severity=f.severity,
        title=f.title,
        body=f.rationale,
        created_at=f.fired_at,
    )


@router.post("/{claim_id}/validate-evidence", response_model=ValidateEvidenceResponse)
async def validate_evidence(
    claim_id: str,
    db: AsyncSession = Depends(get_db),
) -> ValidateEvidenceResponse:
    """Run the targeted evidence-validation AI pass and return findings.

    Works on any claim regardless of pipeline_mode. If no chart text has
    been attached yet (claim.extracted_text is empty), the AI returns a
    single warning explaining that. Otherwise it returns one finding per
    billed code (critical / warning / ok) plus any global documentation
    completeness findings.

    Existing AI-EVIDENCE-V1 findings on this claim are replaced.
    """
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    try:
        findings = await ai_service.validate_evidence(claim_id, db)
    except ai_service.EvidenceValidationError as e:
        # Expected, explainable failure (AI down / truncated / unparseable) —
        # surface the clear message to the user verbatim.
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception("validate_evidence failed for %s: %s", claim_id, e)
        raise HTTPException(status_code=502, detail=f"Evidence validation failed: {e}")

    return ValidateEvidenceResponse(
        claim_id=claim_id,
        chart_text_chars=len(claim.extracted_text or ""),
        findings=[_f_to_out(f) for f in findings],
    )


@router.get("/{claim_id}/evidence-findings", response_model=List[EvidenceFindingOut])
async def list_evidence_findings(
    claim_id: str,
    db: AsyncSession = Depends(get_db),
) -> List[EvidenceFindingOut]:
    """List the most recent evidence-validation findings for a claim
    (read-only; doesn't trigger a new run)."""
    res = await db.execute(
        select(Finding)
        .where(Finding.claim_id == claim_id)
        .where(Finding.detector_id == ai_service.EVIDENCE_DETECTOR_ID)
        .order_by(Finding.fired_at.asc())
    )
    return [_f_to_out(f) for f in res.scalars().all()]
