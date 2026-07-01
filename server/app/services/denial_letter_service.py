"""Generate a standard-style claim denial letter as a PDF and persist it as a
Document attached to the claim (and its case).

Structure is deterministic (a fixed, professional denial notice filled with the
claim data, the headline CMS CARC code, and a per-finding code table), plus an
optional short plain-English paragraph written by the fast model (Haiku) when
``ai_suggestions_enabled`` is on. The letter is regenerated in place — any prior
denial letter for the claim is removed first — so re-running analysis or
re-denying never piles up duplicates.

Public API:
    generate_denial_letter(db, claim, *, user_id=None) -> Document
    regenerate_if_exists(db, claim, *, user_id=None) -> Document | None
    has_denial_letter(db, claim_id) -> bool
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..detectors import denial_codes
from ..models.claims import Claim
from ..models.reference import Member, ProviderOrg
from ..models.workflow import Document, Finding, OpaCase, RuntimeConfig
from ..services.prepay_intake_service import UPLOAD_DIR
from ..utils.markdown_pdf import markdown_to_pdf

logger = logging.getLogger(__name__)

DENIAL_LETTER_KIND = "denial_letter"

_APPEAL_RIGHTS = (
    "You or your authorized representative have the right to appeal this "
    "decision. A written request for reconsideration must be filed within sixty "
    "(60) calendar days of the date of this notice, pursuant to 42 CFR "
    "§422.560 and §422.582. Submit appeals in writing to the address on "
    "file and include this notice along with any supporting clinical "
    "documentation, operative reports, or coding rationale you wish to be "
    "considered."
)


async def _ai_enabled(db: AsyncSession) -> bool:
    row = (await db.execute(
        select(RuntimeConfig).where(RuntimeConfig.key == "ai_suggestions_enabled")
    )).scalar_one_or_none()
    if not row:
        return True
    return row.value.lower() == "true"


def _primary_finding(findings: list[Finding]) -> Optional[Finding]:
    """The finding that best represents the denial: highest confidence, earliest."""
    if not findings:
        return None
    return sorted(
        findings,
        key=lambda f: (-(f.confidence or 0.0), f.fired_at or ""),
    )[0]


async def _haiku_paragraph(
    db: AsyncSession, claim: Claim, findings: list[Finding],
    primary_code: str, primary_desc: str,
) -> Optional[str]:
    """Best-effort 2–3 sentence plain-English denial summary. None on any failure."""
    if not await _ai_enabled(db):
        return None
    try:
        from ..config import settings
        from ..services.ai_service import _client
        client = _client()
        finding_lines = "\n".join(
            f"- {f.detector_id}: {(f.issue_summary or f.rationale or '').strip()}"
            for f in findings[:8]
        ) or "- (no specific findings recorded)"
        user_msg = (
            f"A pre-payment claim has been denied. Primary denial reason: "
            f"CARC {primary_code} — {primary_desc}.\n"
            f"Findings:\n{finding_lines}\n\n"
            "Write 2–3 sentences, in plain professional English for the billing "
            "provider, summarizing why this claim was denied. Do not restate the "
            "CARC code, do not add a greeting or sign-off, no markdown."
        )
        resp = await client.messages.create(
            model=settings.fast_model,  # Haiku tier — ANTHROPIC_MODEL_FAST
            max_tokens=220,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        ).strip()
        return text or None
    except Exception as e:
        logger.info("Denial-letter Haiku paragraph skipped: %s", e)
        return None


async def _build_markdown(db: AsyncSession, claim: Claim, findings: list[Finding]) -> str:
    today = datetime.utcnow().strftime("%B %d, %Y")

    mem = (await db.execute(
        select(Member).where(Member.member_id == claim.member_id)
    )).scalar_one_or_none()
    patient = f"{mem.first_name} {mem.last_name}" if mem else "Member"
    dob = (mem.date_of_birth if mem else None) or "N/A"

    org = (await db.execute(
        select(ProviderOrg).where(ProviderOrg.provider_org_id == claim.provider_org_id)
    )).scalar_one_or_none()
    provider = org.name if org else "Provider"

    billed = float(getattr(claim, "total_billed", 0) or 0)
    dos = getattr(claim, "service_from_date", None) or "N/A"

    primary = _primary_finding(findings)
    p_code, p_desc = denial_codes.denial_code(primary.detector_id if primary else None)

    para = await _haiku_paragraph(db, claim, findings, p_code, p_desc)

    lines: list[str] = []
    lines.append("# NOTICE OF CLAIM DENIAL")
    lines.append("")
    lines.append(f"**Date:** {today}  ")
    lines.append(f"**Claim ID:** {claim.icn}  ")
    lines.append(f"**Member:** {patient} (DOB: {dob})  ")
    lines.append(f"**Provider:** {provider}  ")
    lines.append(f"**Date of Service:** {dos}  ")
    lines.append(f"**Billed Amount:** ${billed:,.2f}")
    lines.append("")
    lines.append("Dear Provider,")
    lines.append("")
    lines.append(
        "After review of the claim referenced above, payment has been "
        "**denied**. The primary reason for this determination is:"
    )
    lines.append("")
    lines.append(f"**CARC {p_code} — {p_desc}**")
    lines.append("")
    if para:
        lines.append(para)
        lines.append("")

    if findings:
        lines.append("## Findings Contributing to This Denial")
        lines.append("")
        lines.append("| CMS Denial Code | Issue |")
        lines.append("| --- | --- |")
        for f in findings:
            code, _ = denial_codes.denial_code(f.detector_id)
            issue = (f.issue_summary or f.rationale or "").strip().replace("\n", " ")
            if len(issue) > 200:
                issue = issue[:197] + "..."
            # Escape pipes so they don't break the markdown table.
            issue = issue.replace("|", "\\|")
            lines.append(f"| CARC {code} | {issue} |")
        lines.append("")

    lines.append("## Your Appeal Rights")
    lines.append("")
    lines.append(_APPEAL_RIGHTS)
    lines.append("")
    lines.append("If you have questions, contact Provider Services at 1-800-555-0100.")
    lines.append("")
    lines.append("Sincerely,  ")
    lines.append("Payment Integrity Unit")
    return "\n".join(lines)


async def _delete_existing(db: AsyncSession, claim_id: str) -> None:
    existing = (await db.execute(
        select(Document).where(
            Document.claim_id == claim_id,
            Document.kind == DENIAL_LETTER_KIND,
        )
    )).scalars().all()
    for d in existing:
        try:
            from pathlib import Path
            if d.file_path:
                Path(d.file_path).unlink(missing_ok=True)
        except Exception:
            pass
        await db.delete(d)


async def generate_denial_letter(
    db: AsyncSession, claim: Claim, *, user_id: Optional[str] = None
) -> Document:
    """Render the denial letter PDF and persist it as a Document (replacing any
    prior denial letter for the claim). Caller commits the session."""
    findings = list((await db.execute(
        select(Finding)
        .where(Finding.claim_id == claim.claim_id)
        .order_by(Finding.fired_at.asc())
    )).scalars().all())

    md = await _build_markdown(db, claim, findings)
    pdf_bytes = markdown_to_pdf(md, title=f"Denial Letter — {claim.icn}")

    await _delete_existing(db, claim.claim_id)

    # Link to the case too, if one exists, so the letter shows on either view.
    case = (await db.execute(
        select(OpaCase).where(OpaCase.claim_id == claim.claim_id)
    )).scalar_one_or_none()

    stored_name = f"{claim.claim_id[:8]}_{uuid.uuid4().hex[:8]}_denial_letter.pdf"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / stored_name
    dest.write_bytes(pdf_bytes)

    doc = Document(
        document_id=str(uuid.uuid4()),
        claim_id=claim.claim_id,
        case_id=case.case_id if case else None,
        filename=stored_name,
        file_path=str(dest),
        file_size_kb=max(1, len(pdf_bytes) // 1024),
        kind=DENIAL_LETTER_KIND,
        uploaded_at=datetime.utcnow().isoformat(),
        uploaded_by_user_id=user_id,
    )
    db.add(doc)
    await db.flush()
    return doc


async def has_denial_letter(db: AsyncSession, claim_id: str) -> bool:
    row = (await db.execute(
        select(Document.document_id).where(
            Document.claim_id == claim_id,
            Document.kind == DENIAL_LETTER_KIND,
        )
    )).first()
    return row is not None


async def regenerate_if_exists(
    db: AsyncSession, claim: Claim, *, user_id: Optional[str] = None
) -> Optional[Document]:
    """Regenerate the denial letter only if one already exists for the claim."""
    if not await has_denial_letter(db, claim.claim_id):
        return None
    return await generate_denial_letter(db, claim, user_id=user_id)
