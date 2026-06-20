"""Re-run a case's evaluation after new evidence (a document) is attached.

When an 837 / medical record is linked to an existing case, both the Rules and
the Evidence verdicts may change now that more is known about the encounter, so
we re-run:

  - Rules    → DetectorService.run_for_case (replaces findings; recomputes
               posterior likelihood + priority).
  - Evidence → ai_service.validate_evidence (chart-vs-billed-codes, the
               AI-EVIDENCE-V1 findings) AND evidence_scanner_service.scan_claim
               (per ICD/DRG documentation scan → evidence_findings).

Best-effort and fully isolated: the attach has already committed before this
runs, and EACH pass runs on its OWN session, so a failure in any pass (no API
key, a transient LLM error, a poisoned session) is logged and skipped — it can
never roll back the attach or 500 the request that triggered it. Returns a
per-pass status summary for logging.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from ..database import AsyncSessionLocal
from ..models.claims import Claim
from ..models.workflow import OpaCase
from . import ai_service
from .detector_service import DetectorService
from .evidence_scanner_service import scan_claim

logger = logging.getLogger(__name__)


async def reevaluate_case(*, case_id: str, claim_id: str | None) -> dict[str, str]:
    """Re-run Rules + Evidence for a case whose claim just gained a document.

    Runs on fresh sessions, independent of the request session, so it is safe to
    call after the attach has committed.
    """
    summary: dict[str, str] = {}

    # 1. Rules — re-run detectors; recomputes posterior + priority internally.
    try:
        async with AsyncSessionLocal() as session:
            case = (await session.execute(
                select(OpaCase).where(OpaCase.case_id == case_id)
            )).scalar_one_or_none()
            if case is not None:
                await DetectorService(session).run_for_case(case.case_sequence)
                summary["rules"] = "ok"
    except Exception as exc:  # noqa: BLE001 — best-effort, never break attach
        logger.warning("reevaluate rules failed for case %s: %s", case_id, exc)
        summary["rules"] = "error"

    if not claim_id:
        return summary

    # 2. Evidence — chart-vs-claim validation (replaces AI-EVIDENCE-V1 findings).
    try:
        async with AsyncSessionLocal() as session:
            await ai_service.validate_evidence(claim_id, session)
            summary["evidence_validate"] = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("reevaluate validate_evidence failed for claim %s: %s", claim_id, exc)
        summary["evidence_validate"] = "error"

    # 3. Evidence — per ICD/DRG documentation scan (upserts evidence_findings).
    try:
        async with AsyncSessionLocal() as session:
            claim = (await session.execute(
                select(Claim).where(Claim.claim_id == claim_id)
            )).scalar_one_or_none()
            if claim is not None:
                await scan_claim(claim, session)
                await session.commit()  # scan_claim only flushes; caller commits.
                summary["evidence_scan"] = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("reevaluate scan_claim failed for claim %s: %s", claim_id, exc)
        summary["evidence_scan"] = "error"

    return summary
