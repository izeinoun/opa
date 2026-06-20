"""Generate a provider recoupment / overpayment letter as a PDF.

Deterministic assembly (no LLM): every figure — per-finding overpayment, the
ERA payment lines, and the total recouped — is taken verbatim from the case so
the letter is exact and reproducible. The content is rendered to PDF via the
shared markdown→PDF path and saved as a Document (kind='recoupment_letter')
linked to the case, named by case number + claim number.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from pathlib import Path
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.claims import Claim, ClaimPayment835, Transaction835
from ..models.reference import Member, Provider, ProviderOrg
from ..models.workflow import AuditLog, Document, Finding, OpaCase
from ..utils.markdown_pdf import markdown_to_pdf
from .case_service import _DET_CODE_MAP, _DETECTOR_NAME_BY_ID
from .prepay_intake_service import UPLOAD_DIR

EVIDENCE_DETECTOR_ID = "AI-EVIDENCE-V1"
OUTPUT_DIR = UPLOAD_DIR / "output"
DOC_KIND = "recoupment_letter"


class RecoupmentLetterError(Exception):
    """Raised when a recoupment letter can't be generated (case/claim missing)."""


def _money(v: Optional[float]) -> str:
    return f"${(v or 0.0):,.2f}"


def _esc(text: Optional[str]) -> str:
    """Neutralize markdown table/pipe breakage when inlining free text."""
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def _build_markdown(
    *, case: OpaCase, claim: Claim, member: Optional[Member],
    org: Optional[ProviderOrg], provider: Optional[Provider],
    rule_findings: List[Finding], evidence_findings: List[Finding],
    era_txn: Optional[Transaction835], era_lines: List[ClaimPayment835],
    today: str,
) -> str:
    total = case.total_overpayment_amount or 0.0
    member_name = f"{member.first_name} {member.last_name}" if member else "(unknown)"
    member_id = member.member_number if member else "(unknown)"
    dob = member.date_of_birth if member else ""
    org_name = org.name if org else "(unknown organization)"
    prov_name = provider.name if provider else "(rendering provider)"
    prov_npi = (provider.npi if provider else claim.rendering_provider_npi) or ""

    dos = claim.service_from_date or ""
    if claim.service_to_date and claim.service_to_date != claim.service_from_date:
        dos = f"{claim.service_from_date} – {claim.service_to_date}"

    out: List[str] = []
    out.append("# Notice of Overpayment and Recoupment\n")
    out.append(
        f"**Date:** {today}  \n"
        f"**Case Number:** {case.case_number}  \n"
        f"**Claim Number (ICN):** {claim.icn}  \n"
        f"**Line of Business:** {claim.lob}\n"
    )

    out.append("## Provider")
    out.append(f"{org_name}  \nRendering Provider: {prov_name} (NPI {prov_npi})\n")

    out.append("## Member")
    out.append(
        f"{member_name} — Member ID {member_id}"
        + (f" (DOB {dob})" if dob else "")
        + f"  \nDate(s) of Service: {dos}\n"
    )

    out.append("## Summary")
    out.append(
        "Following a payment-integrity review of the claim referenced above, we "
        f"have determined an overpayment of **{_money(total)}**, which is subject "
        f"to recoupment via {case.recommended_recovery_method or 'claim offset'}. "
        "The findings supporting this determination are detailed below.\n"
    )

    # ── Rules triggered ──────────────────────────────────────────────────
    out.append("## Rules Triggered")
    if rule_findings:
        out.append("| Code | Rule | Overpayment | Confidence |")
        out.append("| --- | --- | ---: | ---: |")
        for f in rule_findings:
            code = _DET_CODE_MAP.get(f.detector_id or "") or (f.detector_id or "—")
            name = _DETECTOR_NAME_BY_ID.get(code, code)
            conf = f"{f.confidence:.0%}" if f.confidence is not None else "—"
            out.append(f"| {code} | {_esc(name)} | {_money(f.overpayment_amount)} | {conf} |")
        out.append("")
        out.append("**Detail**\n")
        for f in rule_findings:
            code = _DET_CODE_MAP.get(f.detector_id or "") or (f.detector_id or "—")
            name = _DETECTOR_NAME_BY_ID.get(code, code)
            out.append(f"- **{code} — {name}** ({_money(f.overpayment_amount)}): {(f.rationale or '').strip()}")
        out.append("")
    else:
        out.append("_No automated rule findings on this claim._\n")

    # ── Evidence review (chart-only issues) ──────────────────────────────
    if evidence_findings:
        out.append("## Evidence Review Findings")
        out.append(
            "_Issues identified from the submitted medical documentation that are "
            "not visible in the claim or remittance data alone:_\n"
        )
        for f in evidence_findings:
            sev = (f.severity or "warning").upper()
            title = (f.title or "Evidence finding").strip()
            out.append(f"- **[{sev}] {title}** — {(f.rationale or '').strip()}")
        out.append("")

    # ── ERA / 835 remittance detail ──────────────────────────────────────
    out.append("## Remittance (ERA 835) Detail")
    if era_txn is not None:
        out.append(
            f"ERA {era_txn.transaction_number} — Payer {_esc(era_txn.payer_name)} — "
            f"Payment Date {era_txn.transaction_date} — Transaction Total "
            f"{_money(era_txn.total_amount)}\n"
        )
    if era_lines:
        out.append("| Claim ICN | CPT | Date of Service | Paid | Adjustment | Reason |")
        out.append("| --- | --- | --- | ---: | ---: | --- |")
        for p in era_lines:
            reason = "—"
            codes = getattr(p, "adjustment_codes", None) or []
            if codes:
                reason = f"{codes[0].group_code}-{codes[0].reason_code}"
            out.append(
                f"| {_esc(p.claim_icn)} | {p.cpt_code} | {p.service_date or '—'} | "
                f"{_money(p.paid_amount)} | {_money(p.adjustment_amount)} | {reason} |"
            )
        out.append("")
    else:
        out.append("_No remittance lines on file for this claim._\n")

    # ── Total + response ─────────────────────────────────────────────────
    out.append("## Total Amount to be Recouped")
    out.append(f"**{_money(total)}**\n")

    out.append("## Provider Response")
    deadline = case.provider_response_due_date or case.deadline_date or ""
    out.append(
        "Please remit the overpayment amount shown above, or submit a written "
        "dispute with supporting documentation"
        + (f", on or before **{deadline}**" if deadline else "")
        + ". If no response is received by the due date, the amount will be "
        "recovered via the recovery method noted above.\n"
    )
    out.append("---")
    out.append("_This notice was generated by the OPA payment-integrity platform._")
    return "\n".join(out)


async def generate_recoupment_letter(
    db: AsyncSession, *, case_sequence: int, user_id: Optional[str] = None
) -> Document:
    """Assemble + render the recoupment letter PDF and save it as a Document."""
    case = (await db.execute(
        select(OpaCase).where(OpaCase.case_sequence == case_sequence)
    )).scalar_one_or_none()
    if case is None:
        raise RecoupmentLetterError(f"Case {case_sequence} not found")

    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == case.claim_id)
    )).scalar_one_or_none()
    if claim is None:
        raise RecoupmentLetterError("Claim not found for case")

    member = (await db.execute(
        select(Member).where(Member.member_id == claim.member_id)
    )).scalar_one_or_none()
    org = (await db.execute(
        select(ProviderOrg).where(ProviderOrg.provider_org_id == claim.provider_org_id)
    )).scalar_one_or_none()
    provider = (await db.execute(
        select(Provider).where(Provider.npi == claim.rendering_provider_npi)
    )).scalar_one_or_none()

    findings = list((await db.execute(
        select(Finding)
        .where(Finding.claim_id == claim.claim_id, Finding.status == "active")
        .order_by(Finding.fired_at)
    )).scalars().all())
    rule_findings = [f for f in findings if _DET_CODE_MAP.get(f.detector_id or "")]
    evidence_findings = [f for f in findings if f.detector_id == EVIDENCE_DETECTOR_ID]

    era_txn: Optional[Transaction835] = None
    era_lines: List[ClaimPayment835] = []
    if claim.era_transaction_id:
        era_txn = (await db.execute(
            select(Transaction835).where(Transaction835.transaction_id == claim.era_transaction_id)
        )).scalar_one_or_none()
        if era_txn is not None:
            era_lines = list((await db.execute(
                select(ClaimPayment835)
                .where(
                    ClaimPayment835.transaction_id == era_txn.transaction_id,
                    ClaimPayment835.claim_icn == claim.icn,
                )
                .order_by(ClaimPayment835.cpt_code)
            )).scalars().all())

    md = _build_markdown(
        case=case, claim=claim, member=member, org=org, provider=provider,
        rule_findings=rule_findings, evidence_findings=evidence_findings,
        era_txn=era_txn, era_lines=era_lines, today=_today(),
    )
    pdf_bytes = markdown_to_pdf(md, title=f"{case.case_number} Recoupment Letter")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_case = case.case_number.replace("/", "-")
    safe_claim = (claim.icn or "CLAIM").replace("/", "-")
    filename = f"{safe_case}_{safe_claim}_recoupment_letter.pdf"
    stored_name = f"recoupment_{uuid.uuid4().hex[:8]}_{filename}"
    dest = OUTPUT_DIR / stored_name
    dest.write_bytes(pdf_bytes)

    # One letter per case: drop any prior recoupment letters (rows + files) so
    # (re)generating refreshes the letter instead of accumulating duplicates.
    existing = (await db.execute(
        select(Document).where(
            Document.case_id == case.case_id, Document.kind == DOC_KIND
        )
    )).scalars().all()
    for old in existing:
        try:
            Path(old.file_path).unlink(missing_ok=True)
        except OSError:
            pass
        await db.delete(old)
    await db.flush()

    now = datetime.utcnow().isoformat()
    doc = Document(
        document_id=str(uuid.uuid4()),
        claim_id=claim.claim_id,
        case_id=case.case_id,
        filename=filename,
        file_path=str(dest),
        file_size_kb=max(1, len(pdf_bytes) // 1024),
        kind=DOC_KIND,
        uploaded_at=now,
        uploaded_by_user_id=user_id,
    )
    db.add(doc)
    db.add(AuditLog(
        audit_id=str(uuid.uuid4()),
        case_id=case.case_id,
        claim_id=claim.claim_id,
        actor_user_id=user_id or "system",
        action=f"Recoupment letter generated ({filename})",
        from_state=None, to_state=None, reason=None,
        meta_json="{}",
        created_at=now,
    ))
    await db.commit()
    return doc


def _today() -> str:
    # date.today() is unavailable in some sandboxes only for workflow scripts;
    # in the app process it's fine.
    return datetime.utcnow().date().isoformat()
