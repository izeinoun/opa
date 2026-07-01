"""Generate a short, plain-English, claim-specific explanation for each fired
pre-pay rule, stored on ``findings.issue_summary``.

This backs the PayGuard-style finding card in ClaimGuard: a static rule
description (see ``detectors.rule_descriptions``) followed by a friendly
explanation of why *this* claim tripped *this* rule. The explanation is written
by the fast model (Haiku via ``settings.assistant_model``) so it reads naturally
for a billing provider, rather than surfacing the detector's terse technical
rationale verbatim.

Design constraints (per product spec):
  • Only fired rules get an explanation — we never call the LLM speculatively.
  • Gated behind the ``ai_suggestions_enabled`` runtime flag (default ON), the
    same switch every other LLM feature respects.
  • Fully exception-safe: any failure (LLM unavailable, timeout, bad response)
    leaves ``issue_summary`` untouched, and the UI falls back to the detector's
    raw rationale. This must never break detection or claim viewing.

  Uses the FAST model tier (``settings.fast_model`` / ANTHROPIC_MODEL_FAST).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..detectors import rule_descriptions
from ..models.claims import Claim, ClaimLine, line_diag_codes
from ..models.workflow import Finding, RuntimeConfig

logger = logging.getLogger(__name__)

# Cap concurrent Haiku calls so a claim with many findings doesn't open a dozen
# simultaneous connections.
_MAX_CONCURRENCY = 4

_SYSTEM_PROMPT = (
    "You explain medical claim audit findings to the billing provider in plain, "
    "professional English. Given a rule that flagged a claim and the specifics of "
    "that claim, write ONE or TWO short sentences stating concretely why this "
    "claim triggered this rule. Be specific to the claim (reference the actual "
    "codes, amounts, or missing fields when relevant). Do not restate the rule "
    "generically, do not add a preamble, do not use markdown, and do not give a "
    "recommendation — only explain what was found."
)


async def _ai_enabled(db: AsyncSession) -> bool:
    row = (await db.execute(
        select(RuntimeConfig).where(RuntimeConfig.key == "ai_suggestions_enabled")
    )).scalar_one_or_none()
    if not row:
        return True  # default ON, matching prepay_claims._ai_enabled
    return row.value.lower() == "true"


def _claim_context(claim: Claim, lines: list[ClaimLine]) -> str:
    """Compact, prompt-friendly summary of the claim's billed facts."""
    cpts = [ln.cpt_code for ln in lines if getattr(ln, "cpt_code", None)]
    icd_set: list[str] = []
    for code in [getattr(claim, "primary_icd", None)] + [
        c for ln in lines for c in line_diag_codes(ln)
    ]:
        if code and code not in icd_set:
            icd_set.append(code)
    parts = [
        f"Claim form: {getattr(claim, 'claim_form_type', None) or 'unknown'}",
        f"Care setting: {getattr(claim, 'care_setting', None) or 'unknown'}",
        f"DRG: {getattr(claim, 'drg', None) or 'n/a'}",
        f"CPT/HCPCS billed: {', '.join(cpts) if cpts else 'none'}",
        f"ICD-10 billed: {', '.join(icd_set) if icd_set else 'none'}",
        f"Billed amount: {getattr(claim, 'total_billed', None)}",
    ]
    return "\n".join(parts)


async def _explain_one(
    client: Any, finding: Finding, claim_ctx: str
) -> Optional[str]:
    rule_name = finding.title or finding.detector_id or "Rule"
    generic = rule_descriptions.describe(finding.detector_id) or ""
    user_msg = (
        f"Rule: {rule_name}\n"
        f"What the rule checks: {generic}\n"
        f"Detector finding (technical): {finding.rationale or ''}\n\n"
        f"Claim facts:\n{claim_ctx}\n\n"
        "Explain, in one or two sentences for the billing provider, why this "
        "specific claim triggered this rule."
    )
    resp = await client.messages.create(
        model=settings.fast_model,  # Haiku tier — ANTHROPIC_MODEL_FAST
        max_tokens=160,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip()
    return text or None


async def generate_for_findings(
    db: AsyncSession,
    claim: Claim,
    findings: list[Finding],
    *,
    only_missing: bool = True,
) -> int:
    """Populate ``issue_summary`` on fired findings via the fast model.

    Returns the number of findings updated. Never raises — on any failure it
    logs and returns whatever it managed to complete. Caller is responsible for
    flushing/committing the session.

    only_missing=True (default) skips findings that already carry an
    ``issue_summary``, making this safe to call both at detection time and as a
    lazy backfill on claim view.
    """
    if not findings:
        return 0

    targets = [
        f for f in findings
        if not (only_missing and (f.issue_summary or "").strip())
    ]
    if not targets:
        return 0

    if not await _ai_enabled(db):
        return 0

    try:
        from ..services.ai_service import _client
        client = _client()
    except Exception as e:  # not configured / SDK missing
        logger.info("Finding explanations skipped: %s", e)
        return 0

    # Claim lines for context. Prefer the eagerly-loaded relationship; fall back
    # to a query so this works regardless of how `claim` was fetched.
    lines = list(getattr(claim, "lines", None) or [])
    if not lines:
        lines = list((await db.execute(
            select(ClaimLine).where(ClaimLine.claim_id == claim.claim_id)
        )).scalars().all())
    claim_ctx = _claim_context(claim, lines)

    sem = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def _run(f: Finding) -> tuple[Finding, Optional[str]]:
        async with sem:
            try:
                return f, await _explain_one(client, f, claim_ctx)
            except Exception as e:
                logger.warning(
                    "Finding explanation failed for %s (%s): %s",
                    f.finding_id, f.detector_id, e,
                )
                return f, None

    results = await asyncio.gather(*(_run(f) for f in targets))

    updated = 0
    for f, text in results:
        if text:
            f.issue_summary = text
            updated += 1
    if updated:
        await db.flush()
    return updated
