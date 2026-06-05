"""Helper for recording CPT coverage gaps at detector run time.

Called by DET-18 when a CPT code appears on a claim but has no entries in
cpt_dx_coverage. Performs three side-effects in a single call:
  1. Upserts a row in cpt_coverage_gaps (increments seen_count if exists).
  2. Writes a claim-level AuditLog entry so the gap is traceable.
  3. Logs a WARNING so ops see it in server logs.

Returns an informational DetectorResult (confidence=0, overpayment=0) that
surfaces as an info finding on the case.
"""
import json
import logging
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import DetectorResult
from ..models.reference import CptCoverageGap
from ..models.workflow import AuditLog

logger = logging.getLogger(__name__)


async def record_coverage_gap(
    detector_code: str,
    cpt_code: str,
    claim,
    db: AsyncSession,
) -> DetectorResult:
    """Upsert a gap record, write an audit entry, and return an info finding."""
    now = datetime.utcnow().isoformat()

    existing = (await db.execute(
        select(CptCoverageGap).where(CptCoverageGap.cpt_code == cpt_code)
    )).scalar_one_or_none()

    if existing:
        existing.seen_count += 1
        existing.last_seen_at = now
        existing.last_seen_claim_id = claim.claim_id
    else:
        db.add(CptCoverageGap(
            cpt_code=cpt_code,
            first_seen_at=now,
            last_seen_at=now,
            seen_count=1,
            last_seen_claim_id=claim.claim_id,
        ))

    # Resolve system.bot — same fallback used by AuditLogDAO.
    row = (await db.execute(
        text("SELECT user_id FROM opa_users WHERE username = 'system.bot' LIMIT 1")
    )).fetchone()
    system_user_id = row[0] if row else "system"

    db.add(AuditLog(
        claim_id=claim.claim_id,
        actor_user_id=system_user_id,
        action="COVERAGE_GAP_DETECTED",
        meta_json=json.dumps({
            "cpt_code": cpt_code,
            "detector": detector_code,
            "claim_id": claim.claim_id,
        }),
        created_at=now,
    ))

    logger.warning(
        "[%s] CPT %s has no coverage rules in cpt_dx_coverage (claim %s) — gap registered",
        detector_code, cpt_code, claim.claim_id,
    )

    return DetectorResult(
        detector_code=detector_code,
        finding_type="MISSING_COVERAGE_RULE",
        description=(
            f"CPT {cpt_code} has no coverage rules in the reference catalogue. "
            f"Medical necessity cannot be evaluated deterministically for this code. "
            f"Add coverage rules via Admin → Reference Data → CPT/DX Coverage, "
            f"or assign for manual review."
        ),
        overpayment_amount=0.0,
        confidence_score=0.0,
        evidence={
            "cpt_code": cpt_code,
            "gap_registered": True,
            "action_required": "add_coverage_rules",
        },
    )
