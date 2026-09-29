"""Two-stage capacity funnel over the live worklist.

Turns the model's calibrated output into an operational audit plan on *real
cases* (the tuning trial itself is on synthetic rows with no dollars):

  Stage 1 — GATE: keep only cases whose calibrated-RF P(overpayment) clears
    `probability_cutoff` (default 0.80). Below-gate cases are excluded — the
    model isn't confident they're overpayments. This is the Recall/Precision
    cutoff, and it kills the "big dollars × tiny probability" noise (a 2%-likely
    case never reaches the list no matter how large).
  Stage 2 — RANK & CUT: among survivors, rank by EV = probability × amount and
    keep the top `capacity` (the team's monthly bandwidth). Survivors beyond the
    line are backlog "left on the table". The preview returns the top `capacity`
    plus `backlog_preview` rows so the cut is visible.

Probability = the CALIBRATED RandomForest score (provider.billing_variance_score),
the same score the tuning panel produces — retuning the model moves this funnel.
Deliberately NOT the detector evidence score, which clusters near 1.0.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.reference import Provider
from ..models.workflow import OpaCase
from ..schemas.admin_schemas import CapacityCaseRow, CapacityPreviewResponse, EvCurvePoint

# Fallback P(overpayment) when a case has no resolvable provider RF score and no
# stored prior — a neutral guess that keeps the case in the ranking.
_DEFAULT_PROB = 0.30


def _case_probability(case: OpaCase, score_by_npi: dict) -> float:
    """Calibrated P(overpayment) for a case, in priority order:
      1. Stage 2 claim predictor — claims.overpayment_probability (per-claim).
      2. Stage 1 provider RF score — provider.billing_variance_score (fallback).
      3. The case's stored prior (composite_likelihood), then _DEFAULT_PROB.
    Stage 2 is the intended source; the provider score is the pre-Stage-2 fallback
    for claims not yet scored."""
    claim = case.claim
    if claim is not None and getattr(claim, "overpayment_probability", None) is not None:
        return float(claim.overpayment_probability)
    npi = claim.rendering_provider_npi if claim is not None else None
    score = score_by_npi.get(npi) if npi else None
    if score is not None:
        return float(score)
    ls = case.likelihood_score
    if ls is not None and ls.composite_likelihood is not None:
        return float(ls.composite_likelihood)
    return _DEFAULT_PROB


async def compute_capacity_preview(
    session: AsyncSession,
    capacity: Optional[int] = None,
    target_capture: Optional[float] = None,
    probability_cutoff: float = 0.80,
    backlog_preview: int = 25,
) -> CapacityPreviewResponse:
    """EV-first audit plan over the open worklist.

    1. GATE — keep only cases with calibrated P(overpayment) ≥ `probability_cutoff`
       (a light secondary filter; the rest are excluded as low-confidence).
    2. RANK — order survivors by EV = probability × amount, descending.
    3. CUT — by ONE of two operational knobs, each derivable from the other:
         • `capacity`       → work the top N cases; report the EV capture ratio.
         • `target_capture` → capture this fraction of total EV; report the N (capacity) needed.
       Exactly one is the driver; the other is computed. If both are None, no cut.
    """
    cutoff = max(0.0, min(1.0, float(probability_cutoff)))
    backlog_preview = max(0, int(backlog_preview))

    # Open worklist = everything not in a terminal (closed_*) status. Closed cases
    # are finished work and don't consume this month's review budget.
    rows = (await session.execute(
        select(OpaCase).where(OpaCase.status.notlike("closed_%"))
    )).scalars().all()

    # One query for both the display name and the calibrated RF score (the
    # probability driver) keyed by NPI.
    npis = {
        c.claim.rendering_provider_npi
        for c in rows
        if c.claim is not None and c.claim.rendering_provider_npi
    }
    name_by_npi: dict[str, str] = {}
    score_by_npi: dict[str, Optional[float]] = {}
    if npis:
        prov = (await session.execute(
            select(Provider.npi, Provider.name, Provider.billing_variance_score)
            .where(Provider.npi.in_(npis))
        )).all()
        name_by_npi = {npi: name for npi, name, _ in prov}
        score_by_npi = {npi: score for npi, _, score in prov}

    # Per-case records with calibrated probability, amount, and EV.
    recs = []
    for c in rows:
        prob = _case_probability(c, score_by_npi)
        amount = float(c.total_overpayment_amount or 0.0)
        npi = c.claim.rendering_provider_npi if c.claim is not None else None
        recs.append({
            "case_id": c.case_id,
            "case_number": c.case_number,
            "provider": name_by_npi.get(npi) or npi or "—",
            "amount": amount,
            "prob": prob,
            "ev": round(prob * amount, 2),
        })

    total_open = len(recs)

    # Stage 1: confidence gate.
    survivors = [r for r in recs if r["prob"] >= cutoff]
    gate_passed = len(survivors)
    gate_excluded = total_open - gate_passed

    # Rank survivors by EV (desc), tie-break by amount.
    ranked = sorted(survivors, key=lambda r: (r["ev"], r["amount"]), reverse=True)
    total_ev = round(sum(r["ev"] for r in ranked), 2)

    # Resolve the cut. target_capture (if given) drives capacity; else capacity drives.
    if target_capture is not None:
        target = max(0.0, min(1.0, float(target_capture)))
        # Smallest N whose cumulative EV covers `target` of the total.
        needed, cum = 0, 0.0
        if total_ev > 0:
            for r in ranked:
                cum += r["ev"]
                needed += 1
                if cum / total_ev >= target:
                    break
        capacity = needed
    else:
        capacity = max(0, int(capacity if capacity is not None else 0))

    within_count = min(capacity, gate_passed)
    backlog_count = max(0, gate_passed - capacity)
    captured_ev = round(sum(r["ev"] for r in ranked[:capacity]), 2)
    backlog_ev = round(sum(r["ev"] for r in ranked[capacity:]), 2)
    capture_ratio = round(captured_ev / total_ev, 4) if total_ev > 0 else 0.0
    cut_line = ranked[capacity - 1]["ev"] if 0 < capacity <= gate_passed else None

    # Cumulative-EV curve (capture ratio vs # cases), starting at (0, 0) and
    # downsampled to ≤ _CURVE_POINTS so the line stays cheap on large worklists.
    _CURVE_POINTS = 120
    curve: list[EvCurvePoint] = [EvCurvePoint(n=0, capture_ratio=0.0)]
    if gate_passed > 0 and total_ev > 0:
        step = max(1, gate_passed // _CURVE_POINTS)
        cum = 0.0
        for i, r in enumerate(ranked, 1):
            cum += r["ev"]
            if i % step == 0 or i == gate_passed:
                curve.append(EvCurvePoint(n=i, capture_ratio=round(cum / total_ev, 4)))

    # Show the within-capacity set plus a preview of what's left on the table.
    show_n = min(len(ranked), capacity + backlog_preview)
    out_rows = [
        CapacityCaseRow(
            rank=i + 1,
            case_id=r["case_id"],
            case_number=r["case_number"],
            provider=r["provider"],
            amount_at_risk=r["amount"],
            probability=round(r["prob"], 4),
            ev=r["ev"],
            within_capacity=(i + 1) <= capacity,
        )
        for i, r in enumerate(ranked[:show_n])
    ]

    return CapacityPreviewResponse(
        probability_cutoff=cutoff,
        capacity=capacity,
        total_open_cases=total_open,
        gate_passed=gate_passed,
        gate_excluded=gate_excluded,
        within_capacity_count=within_count,
        backlog_count=backlog_count,
        total_ev=total_ev,
        captured_ev=captured_ev,
        backlog_ev=backlog_ev,
        capture_ratio=capture_ratio,
        ev_cut_line=cut_line,
        ev_curve=curve,
        rows=out_rows,
    )
