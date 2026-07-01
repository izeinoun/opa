from __future__ import annotations

from typing import Optional, Tuple
from datetime import date

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.workflow import PrioritizationConfig, OpaCase, Finding, CaseFinding, LikelihoodScore
from ..models.claims import ClaimLine
from .scoring_service import ScoringService
from .case_service import _compute_evidence_score
from .amount_at_risk import compute_at_risk_deduped


_SINGLETON_ID = "current"


async def get_config(db: AsyncSession) -> PrioritizationConfig:
    """Fetch the singleton prioritization config, creating it with defaults if missing."""
    result = await db.execute(
        select(PrioritizationConfig).where(PrioritizationConfig.config_id == _SINGLETON_ID)
    )
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = PrioritizationConfig(config_id=_SINGLETON_ID)
        db.add(cfg)
        await db.flush()
    return cfg


def compute_priority_with_config(
    cfg: PrioritizationConfig,
    *,
    amount_at_risk: float,
    evidence: float,
    deadline: Optional[date],
) -> Tuple[float, str]:
    """Apply the saved config to ScoringService.compute_priority (Option B / EMV)."""
    return ScoringService().compute_priority(
        amount_at_risk=amount_at_risk,
        evidence=evidence,
        deadline=deadline,
        max_amount=cfg.amount_cap,
        severity_weight=cfg.severity_weight,
        urgency_weight=cfg.urgency_weight,
        urgency_window_days=cfg.urgency_window_days,
        high_threshold=cfg.high_threshold,
        medium_threshold=cfg.medium_threshold,
    )


async def recompute_open_cases(db: AsyncSession, cfg: PrioritizationConfig) -> dict:
    """Recompute priority_score / priority for every open (is_active=True) case using cfg.

    Returns a summary {scanned, updated, skipped, errors}.
    """
    result = await db.execute(select(OpaCase).where(OpaCase.is_active == True))  # noqa: E712
    cases = list(result.scalars().all())

    scanned = len(cases)
    updated = 0
    skipped = 0
    errors = 0

    for case in cases:
        try:
            findings_res = await db.execute(
                select(Finding)
                .join(CaseFinding, Finding.finding_id == CaseFinding.finding_id)
                .where(CaseFinding.case_id == case.case_id)
            )
            findings = list(findings_res.scalars().all())

            ls_res = await db.execute(
                select(LikelihoodScore).where(LikelihoodScore.case_id == case.case_id)
            )
            ls = ls_res.scalar_one_or_none()
            prior = ls.composite_likelihood if ls is not None else 0.5
            evidence = _compute_evidence_score(findings, leak=cfg.rule_leak)

            try:
                deadline = date.fromisoformat(case.deadline_date) if case.deadline_date else None
            except Exception:
                deadline = None

            # Recompute amount_at_risk via per-line de-dup so it's never inflated.
            # The deduped value is authoritative — always write it back, even if 0.
            # A naive sum from prior writers (e.g. seed scripts) would double-count
            # any line flagged by multiple detectors.
            lines_res = await db.execute(
                select(ClaimLine).where(ClaimLine.claim_id == case.claim_id)
            )
            claim_lines = list(lines_res.scalars().all())
            deduped_at_risk, _ = compute_at_risk_deduped(claim_lines, findings)
            case.total_overpayment_amount = deduped_at_risk

            score, band = compute_priority_with_config(
                cfg,
                amount_at_risk=case.total_overpayment_amount or 0.0,
                evidence=evidence,
                deadline=deadline,
            )

            case.priority_score = score
            case.priority = band
            if ls is not None:
                ls.priority_score = score
            updated += 1
        except Exception:
            errors += 1
            continue

    await db.flush()
    return {"scanned": scanned, "updated": updated, "skipped": skipped, "errors": errors}
