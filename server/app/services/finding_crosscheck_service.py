"""Finding cross-check — a single holistic LLM pass over a claim's primary
("Key issues") findings that adds a one-sentence *distinction note* to any
finding whose explanation overlaps another's.

Two detectors can be logically distinct yet narrate the same underlying fact
(e.g. FWA-02 flags the provider's specialty for a code while FWA-03 flags the
place-of-service for that same code — both end up saying "this hospital code
doesn't belong in an office visit"). To a reviewer they read as duplicates.
This pass names the overlap and states, per finding, how it differs from its
sibling — full transparency without merging or suppressing anything.

Design (mirrors finding_explanation_service):
  • ONE call over the whole key set (never pairwise) — cluster-aware and cheap.
  • Only findings that genuinely overlap get a note; distinct findings get none.
  • Never mutates the detector's own rationale/issue_summary; the note is stored
    separately in findings.evidence JSON (key "distinction_note"), clearly
    LLM-authored, so the deterministic text and audit trail stay intact.
  • Gated by ai_suggestions_enabled; fully exception-safe (any failure leaves
    findings untouched and the UI simply shows no notes).
  • Idempotent: a "_crosscheck" flag in the evidence JSON marks findings already
    processed, so this is safe to call at audit time AND as a lazy read backfill.

Caller is responsible for committing the session.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..detectors import rule_descriptions
from ..config import settings
from ..models.claims import Claim
from ..models.workflow import Finding, RuntimeConfig

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You review a set of automated audit findings on ONE medical claim. Some "
    "findings come from different rules yet describe the SAME underlying problem "
    "from different angles — to a reviewer they read as duplicates. Your job is "
    "transparency, not merging: for each finding that meaningfully overlaps "
    "another, write ONE short sentence (max ~25 words) telling the reviewer how "
    "THIS finding differs from the one it overlaps, naming the other rule by its "
    "code. If a finding is distinct from all others, give it no note. Never "
    "restate the finding, never give a recommendation, never use markdown. "
    'Respond ONLY with JSON: {"notes": {"<finding_id>": "<sentence>", ...}} '
    "including only findings that overlap another."
)


async def _ai_enabled(db: AsyncSession) -> bool:
    row = (await db.execute(
        select(RuntimeConfig).where(RuntimeConfig.key == "ai_suggestions_enabled")
    )).scalar_one_or_none()
    if not row:
        return True  # default ON, matching prepay_claims._ai_enabled
    return row.value.lower() == "true"


def _load_evidence(finding: Finding) -> dict:
    try:
        data = json.loads(finding.evidence) if finding.evidence else {}
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def distinction_note_of(finding: Finding) -> Optional[str]:
    """Read-side helper: the persisted distinction note, or None."""
    note = _load_evidence(finding).get("distinction_note")
    return note if isinstance(note, str) and note.strip() else None


def _already_checked(findings: list[Finding]) -> bool:
    """True when every finding has been through a cross-check pass already."""
    return all(_load_evidence(f).get("_crosscheck") is True for f in findings)


def _finding_prompt_block(finding: Finding) -> str:
    code = finding.detector_id or "RULE"
    desc = rule_descriptions.describe(finding.detector_id) or ""
    explanation = (finding.issue_summary or finding.rationale or "").strip()
    return (
        f"- finding_id: {finding.finding_id}\n"
        f"  rule: {code}\n"
        f"  checks: {desc}\n"
        f"  finding: {explanation}"
    )


async def crosscheck_findings(
    db: AsyncSession,
    claim: Claim,
    key_findings: list[Finding],
    *,
    only_missing: bool = True,
) -> dict:
    """Add distinction notes to overlapping findings in the key set.

    Returns {finding_id: note} for findings that got a note this run (empty on
    skip/failure). Persists notes + a processed flag into each finding's
    evidence JSON; never raises.
    """
    # Need at least two findings for anything to overlap.
    if len(key_findings) < 2:
        # Still mark a lone finding processed so we don't retry every view.
        for f in key_findings:
            _persist(f, note=None)
        return {}

    if only_missing and _already_checked(key_findings):
        return {}

    if not await _ai_enabled(db):
        return {}

    try:
        from ..services.ai_service import _client, MODEL
        client = _client()
    except Exception as e:  # not configured / SDK missing
        logger.info("Finding cross-check skipped: %s", e)
        return {}

    blocks = "\n".join(_finding_prompt_block(f) for f in key_findings)
    user_msg = (
        f"Findings on this claim:\n{blocks}\n\n"
        "Return the JSON described in the instructions."
    )

    try:
        resp = await client.messages.create(
            model=settings.fast_model,   # Haiku tier — same as per-finding explanations
            max_tokens=600,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        ).strip()
        notes = _parse_notes(text)
    except Exception as e:
        logger.warning("Finding cross-check failed for %s: %s", claim.claim_id, e)
        return {}

    valid_ids = {f.finding_id for f in key_findings}
    applied: dict = {}
    for f in key_findings:
        note = notes.get(f.finding_id)
        note = note.strip() if isinstance(note, str) and note.strip() else None
        _persist(f, note=note)
        if note:
            applied[f.finding_id] = note
    # Drop any hallucinated ids that don't belong to this claim's key set.
    for stray in set(notes) - valid_ids:
        logger.debug("Cross-check returned unknown finding_id %s — ignored", stray)

    await db.flush()
    return applied


def _persist(finding: Finding, *, note: Optional[str]) -> None:
    """Read-modify-write the evidence JSON, preserving existing keys."""
    data = _load_evidence(finding)
    data["_crosscheck"] = True
    if note:
        data["distinction_note"] = note
    else:
        data.pop("distinction_note", None)
    finding.evidence = json.dumps(data)


def _parse_notes(text: str) -> dict:
    """Extract {finding_id: note} from the model's JSON reply, robustly."""
    if not text:
        return {}
    try:
        from ..services.ai_service import _extract_json_object
        obj = _extract_json_object(text)
    except Exception:
        try:
            obj = json.loads(text)
        except (ValueError, TypeError):
            return {}
    if not isinstance(obj, dict):
        return {}
    notes = obj.get("notes", obj)   # tolerate a bare mapping
    return notes if isinstance(notes, dict) else {}
