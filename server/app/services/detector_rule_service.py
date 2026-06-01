from __future__ import annotations

from typing import Dict, List, Set, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.workflow import DetectorRuleConfig


# Detectors safe to run against a pre-pay claim. Excludes DET-04 (fee
# schedule mispricing) because pre-pay claims have no `total_paid` yet —
# the rule has nothing to compare against. Everything else (duplicate,
# eligibility, NCCI/MUE, excluded provider, coding errors, FWA detectors)
# is meaningful before payment.
PREPAY_SAFE_CODES: set[str] = {
    "DET-01",   # duplicate billing
    "DET-02",   # retro eligibility
    "DET-06",   # NCCI / MUE
    "DET-08",   # excluded provider
    "DET-09",   # coding errors
    "FWA-02",   # credential mismatch
    "FWA-03",   # POS mismatch
}


# Single source of truth for rule metadata. The DB stores enabled/score; this map
# supplies the human-facing name and description applied on first seed.
_RULE_DEFAULTS: List[Dict[str, str]] = [
    {
        "rule_code": "DET-01",
        "name": "Duplicate Billing",
        "description": "Detects exact and near-duplicate claim submissions for the same member, provider, date, and procedure.",
    },
    {
        "rule_code": "DET-02",
        "name": "Retro Eligibility",
        "description": "Flags services billed after the member's coverage was retroactively terminated or never effective.",
    },
    {
        "rule_code": "DET-04",
        "name": "Fee Schedule Mispricing",
        "description": "Identifies paid amounts that exceed the contracted or CMS fee schedule allowed amount.",
    },
    {
        "rule_code": "DET-06",
        "name": "NCCI / MUE Violation",
        "description": "Detects unbundled procedure pairs and unit counts above CMS Medically Unlikely Edits limits.",
    },
    {
        "rule_code": "DET-08",
        "name": "Excluded Provider",
        "description": "Flags claims rendered by providers on the HHS OIG exclusion list — a hard compliance violation.",
    },
    {
        "rule_code": "DET-09",
        "name": "Coding Errors",
        "description": "Detects upcoding, DX/CPT mismatches, and other coding accuracy issues.",
    },
    # FWA detectors — deterministic. FWA-04 + FWA-07 are LLM-assisted and
    # live outside the orchestrator, so they aren't toggleable via this
    # config table (they're gated by the ANTHROPIC_API_KEY presence instead).
    {
        "rule_code": "FWA-02",
        "name": "Credential Misrepresentation",
        "description": "Compares rendering provider's specialty against the typical specialty for each billed CPT. Flags claims where the provider's NPI taxonomy doesn't fit the billed procedures.",
    },
    {
        "rule_code": "FWA-03",
        "name": "Place-of-Service Mismatch",
        "description": "Flags claim lines where the billed POS code is inconsistent with the procedure type (e.g. inpatient-only CPT billed with an office POS).",
    },
]


async def seed_defaults(db: AsyncSession) -> None:
    """Insert any missing rule rows with defaults (enabled=True, score=1.0)."""
    result = await db.execute(select(DetectorRuleConfig.rule_code))
    existing = {r for (r,) in result.all()}
    added = False
    for spec in _RULE_DEFAULTS:
        if spec["rule_code"] in existing:
            continue
        db.add(DetectorRuleConfig(
            rule_code=spec["rule_code"],
            name=spec["name"],
            description=spec["description"],
        ))
        added = True
    if added:
        await db.flush()


async def get_all(db: AsyncSession) -> List[DetectorRuleConfig]:
    await seed_defaults(db)
    result = await db.execute(
        select(DetectorRuleConfig).order_by(DetectorRuleConfig.rule_code)
    )
    return list(result.scalars().all())


async def get_runtime_config(db: AsyncSession) -> tuple[Set[str], Dict[str, float]]:
    """Returns (enabled_codes, score_multipliers_by_code)."""
    rules = await get_all(db)
    enabled = {r.rule_code for r in rules if r.enabled}
    multipliers = {r.rule_code: r.score for r in rules}
    return enabled, multipliers


async def get_by_code(db: AsyncSession, rule_code: str) -> Optional[DetectorRuleConfig]:
    result = await db.execute(
        select(DetectorRuleConfig).where(DetectorRuleConfig.rule_code == rule_code)
    )
    return result.scalar_one_or_none()
