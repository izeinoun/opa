"""Per-finding accept/reject/adjust workflow.

A FindingDisposition row exists for every finding. The initial status is
seeded by default_disposition_for() based on the detector + confidence.
Analysts can later change it via accept/reject/adjust endpoints.

Status semantics for the at-risk calculation (see amount_at_risk.py):
  accepted     → the finding's claim contributes normally
  adjusted     → the finding's claim contributes its adjusted_amount instead
                  of the system-derived amount
  rejected     → contributes nothing
  needs_review → contributes nothing AND blocks the case from advancing
                  out of in_review (case_service.transition gate)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.workflow import Finding, FindingDisposition


# Detector classes:
#   - "deterministic" detectors fire on hard rules / lookups
#   - "llm" detectors involve AI judgment and need analyst review at MEDIUM
LLM_DETECTORS = {"DET-09"}


def default_disposition_for(finding: Finding) -> str:
    """Initial disposition based on detector type and confidence."""
    if finding.detector_id in LLM_DETECTORS:
        if finding.confidence >= 0.85:
            return "accepted"     # HIGH — trust it
        if finding.confidence >= 0.65:
            return "needs_review" # MEDIUM — analyst must decide
        return "rejected"         # LOW — auto-reject
    # Deterministic detectors are accepted by default; analyst can still reject.
    return "accepted"


async def ensure_disposition(
    session: AsyncSession,
    finding: Finding,
    case_id: str,
) -> FindingDisposition:
    """Create a default-seeded disposition for the given finding if missing.
    Returns the existing or newly-created disposition row.
    """
    res = await session.execute(
        select(FindingDisposition).where(FindingDisposition.finding_id == finding.finding_id)
    )
    existing = res.scalar_one_or_none()
    if existing:
        return existing

    status = default_disposition_for(finding)
    now = datetime.utcnow().isoformat()
    disposition = FindingDisposition(
        disposition_id=str(uuid4()),
        finding_id=finding.finding_id,
        case_id=case_id,
        status=status,
        original_amount=finding.overpayment_amount or 0.0,
        adjusted_amount=None,
        reason=None,
        decided_by_user_id=None,  # system-seeded
        decided_at=None,
        created_at=now,
    )
    session.add(disposition)
    return disposition


def effective_amount(disposition: FindingDisposition) -> float:
    """The dollar amount this finding actually contributes to the at-risk total.

    accepted   → original_amount
    adjusted   → adjusted_amount (or original if missing)
    rejected   → 0
    needs_review → 0  (provisional — not confirmed)
    """
    if disposition.status in ("rejected", "needs_review"):
        return 0.0
    if disposition.status == "adjusted" and disposition.adjusted_amount is not None:
        return float(disposition.adjusted_amount)
    return float(disposition.original_amount or 0.0)


def is_blocking(disposition: FindingDisposition) -> bool:
    """Whether this disposition blocks the case from advancing out of in_review."""
    return disposition.status == "needs_review"


def compute_at_risk_with_dispositions(
    claim_lines,
    findings,
    dispositions_by_finding_id: dict,
):
    """Disposition-aware wrapper around compute_at_risk_deduped.

    Behavior:
      - findings with disposition status 'rejected' or 'needs_review' are
        filtered out before dedup (contribute $0)
      - findings with status 'adjusted' have their breakdown contribution
        scaled to equal `adjusted_amount`. Per-line attribution stays
        proportional to the original per-line claim
      - findings with no disposition row are treated as 'accepted'

    Returns (total_at_risk, per_line_breakdown) — same shape as
    compute_at_risk_deduped.
    """
    from .amount_at_risk import compute_at_risk_deduped

    active = []
    for f in findings:
        d = dispositions_by_finding_id.get(f.finding_id)
        if d is None:
            active.append(f)
            continue
        if d.status in ("rejected", "needs_review"):
            continue
        active.append(f)

    total, breakdown = compute_at_risk_deduped(claim_lines, active)

    # Scale adjusted-finding contributions to match adjusted_amount
    scaled_breakdown = {}
    finding_contributions: dict = {}
    for line_id, v in breakdown.items():
        finding_contributions.setdefault(v["finding_id"], []).append((line_id, v))

    new_total = 0.0
    for finding_id, line_entries in finding_contributions.items():
        d = dispositions_by_finding_id.get(finding_id)
        scale = 1.0
        if d is not None and d.status == "adjusted" and d.adjusted_amount is not None:
            current = sum(e[1]["amount"] for e in line_entries)
            if current > 0:
                scale = float(d.adjusted_amount) / current
            else:
                scale = 1.0  # finding had no winning lines; scaling can't add anything
        for line_id, v in line_entries:
            new_amt = round(v["amount"] * scale, 2)
            scaled_breakdown[line_id] = {**v, "amount": new_amt}
            new_total += new_amt

    return round(new_total, 2), scaled_breakdown


async def load_dispositions_by_finding(session, finding_ids: list) -> dict:
    """Bulk-load dispositions for a list of finding_ids. Returns {finding_id: row}."""
    from sqlalchemy import select
    if not finding_ids:
        return {}
    res = await session.execute(
        select(FindingDisposition).where(FindingDisposition.finding_id.in_(finding_ids))
    )
    return {d.finding_id: d for d in res.scalars().all()}


async def case_has_blocking_findings(session, case_id: str) -> bool:
    """True if any disposition on this case is in 'needs_review' state."""
    from sqlalchemy import select, func
    res = await session.execute(
        select(func.count(FindingDisposition.disposition_id))
        .where(FindingDisposition.case_id == case_id)
        .where(FindingDisposition.status == "needs_review")
    )
    return (res.scalar_one() or 0) > 0


async def recompute_case_at_risk(session, case_id: str) -> float:
    """Recompute and persist case.total_overpayment_amount honoring current
    dispositions. Returns the new total."""
    from sqlalchemy import select
    from ..models.workflow import OpaCase, Finding, CaseFinding
    from ..models.claims import ClaimLine

    # Pull case + lines + findings
    case_res = await session.execute(select(OpaCase).where(OpaCase.case_id == case_id))
    case = case_res.scalar_one_or_none()
    if case is None:
        return 0.0

    lines_res = await session.execute(
        select(ClaimLine).where(ClaimLine.claim_id == case.claim_id)
    )
    claim_lines = list(lines_res.scalars().all())

    findings_res = await session.execute(
        select(Finding)
        .join(CaseFinding, Finding.finding_id == CaseFinding.finding_id)
        .where(CaseFinding.case_id == case_id)
    )
    findings = list(findings_res.scalars().all())

    dispositions = await load_dispositions_by_finding(
        session, [f.finding_id for f in findings]
    )
    total, _ = compute_at_risk_with_dispositions(claim_lines, findings, dispositions)
    case.total_overpayment_amount = total
    await session.flush()
    return total
