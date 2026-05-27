from __future__ import annotations

from typing import Dict, List, Set, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.workflow import DetectorRuleConfig


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
