"""Enrich an awaiting (835-created) claim with the diagnoses + claim-form
metadata carried by its matched 837, then clear the dx_pending gate.

An 835 remittance has no diagnoses, so its claim is created with a placeholder
primary_icd and dx_pending=True. When the matching 837 links, this service
copies the real Dx (claim-level principal + per-line pointers) and the claim
form type / care setting / bill type / DRG onto the claim, flips the case out of
its 'awaiting_837' state, and writes an audit entry. The caller then re-runs the
full detector + FWA + evidence suite (via reevaluation_service), which now sees
genuine diagnoses — so DET-09 / DET-18 / DET-19 fire meaningfully.

Idempotent: a claim that isn't dx_pending (already enriched, or never awaiting)
is left untouched.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.claims import Claim, ClaimLine
from ..models.workflow import AuditLog, OpaCase
from .edi_parser_837 import Parsed837

logger = logging.getLogger(__name__)


def _assign_line_diags(line: ClaimLine, diags: list[str]) -> None:
    """Write up to four diagnoses onto a claim line's diag_1..diag_4 columns."""
    slots = [None, None, None, None]
    for i, d in enumerate(diags[:4]):
        slots[i] = d
    line.diag_1, line.diag_2, line.diag_3, line.diag_4 = slots


async def enrich_claim_from_837(
    db: AsyncSession, *, claim_id: str, parsed: Parsed837, actor_user_id: str | None = None
) -> bool:
    """Apply the 837's Dx + claim-form metadata to an awaiting claim.

    Returns True if the claim was enriched (was dx_pending), False otherwise.
    Commits its own changes; the caller's subsequent re-evaluation sees them.
    """
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None or not claim.dx_pending:
        return False
    if not parsed.diagnoses:
        # 837 linked but carried no parseable diagnoses — leave the gate set so an
        # analyst can decide (override) rather than silently adjudicating on Z99.9.
        logger.info("837 for claim %s carried no diagnoses; leaving dx_pending", claim_id)
        return False

    # Claim-level diagnoses + form metadata.
    if parsed.principal_dx:
        claim.primary_icd = parsed.principal_dx
    if parsed.claim_type:
        claim.claim_type = parsed.claim_type
    if parsed.claim_form_type:
        claim.claim_form_type = parsed.claim_form_type
    if parsed.care_setting:
        claim.care_setting = parsed.care_setting
    if parsed.bill_type:
        claim.bill_type = parsed.bill_type
    if parsed.drg:
        claim.drg = parsed.drg

    # Per-line diagnoses: match each claim line to a parsed 837 line by CPT
    # (consume in order so repeated CPTs line up), else fall back to principal.
    lines = (await db.execute(
        select(ClaimLine).where(ClaimLine.claim_id == claim_id).order_by(ClaimLine.line_number)
    )).scalars().all()
    remaining = list(parsed.service_lines)
    for line in lines:
        match = next((p for p in remaining if p.cpt == line.cpt_code), None)
        if match is not None:
            remaining.remove(match)
            _assign_line_diags(line, match.diagnoses or ([parsed.principal_dx] if parsed.principal_dx else []))
            if match.revenue_code:
                line.revenue_code = match.revenue_code
        elif parsed.principal_dx:
            _assign_line_diags(line, [parsed.principal_dx])

    claim.dx_pending = False
    claim.updated_at = datetime.utcnow().isoformat()

    # Flip the case out of its awaiting state into the normal worklist.
    case = (await db.execute(
        select(OpaCase).where(OpaCase.claim_id == claim_id)
    )).scalar_one_or_none()
    now = datetime.utcnow().isoformat()
    if case is not None:
        prior = case.status
        if case.status == "awaiting_837":
            case.status = "new"
        case.updated_at = now
        db.add(AuditLog(
            audit_id=str(uuid.uuid4()),
            case_id=case.case_id,
            claim_id=claim_id,
            actor_user_id=actor_user_id or "system",
            action=(
                f"837 linked — diagnoses applied ({', '.join(parsed.diagnoses[:6])}); "
                f"form {parsed.claim_form_type or 'n/a'}; re-evaluating rules"
            ),
            from_state=prior,
            to_state=case.status,
            reason=None,
            meta_json="{}",
            created_at=now,
        ))

    await db.commit()
    logger.info("Enriched claim %s from 837: dx=%s form=%s", claim_id, parsed.diagnoses, parsed.claim_form_type)
    return True
