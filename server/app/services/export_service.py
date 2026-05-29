"""Denial / approval ZIP package + X12 837 generation.

Ported from ClaimGuard's services/{zip_service,x12_service}.py and adapted
to use a normalized ClaimContext dict instead of the standalone ORM model.
"""
from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import datetime
from typing import Any, List


# ── X12 837 generation ────────────────────────────────────────────────────

SENDER_ID = "OPAPLATFORM   "   # 15 chars
RECEIVER_ID = "PAYER001       "  # 15 chars


def _now_ccyymmdd() -> str:
    return datetime.utcnow().strftime("%Y%m%d")


def _now_yymmdd() -> str:
    return datetime.utcnow().strftime("%y%m%d")


def _now_hhmm() -> str:
    return datetime.utcnow().strftime("%H%M")


def _control_number(seed: str) -> str:
    return str(abs(hash(seed)) % 10**9).zfill(9)


def generate_x12(ctx: dict[str, Any]) -> str:
    """Build a single 837P/837I transaction string from a ClaimContext dict.

    Required keys: claim_id, claim_form_type, drg, dos, billed_amount,
    provider, patient, dob, cpts, icd10.
    """
    is_institutional = ctx.get("claim_form_type") == "UB-04"
    transaction_set = "837"
    impl_guide = "005010X223A2" if is_institutional else "005010X222A1"

    icn = _control_number(str(ctx["claim_id"]))
    cpts: List[str] = list(ctx.get("cpts") or [])
    icd10: List[str] = list(ctx.get("icd10") or [])
    billed = float(ctx.get("billed_amount") or 0)

    dos_ccyymmdd = (ctx.get("dos") or "").replace("-", "")
    patient = str(ctx.get("patient") or "")
    patient_last, _, patient_first = patient.partition(" ")
    provider_name = (ctx.get("provider") or "UNKNOWN PROVIDER").upper()[:35]

    s: List[str] = []
    s.append(
        "ISA*00*          *00*          *ZZ*"
        f"{SENDER_ID}*ZZ*{RECEIVER_ID}*"
        f"{_now_yymmdd()}*{_now_hhmm()}*^*00501*{icn}*0*P*:"
    )
    s.append(
        f"GS*HC*OPAPLATFORM*PAYER001*{_now_ccyymmdd()}*{_now_hhmm()}*"
        f"{icn}*X*{impl_guide}"
    )
    s.append(f"ST*{transaction_set}*0001*{impl_guide}")
    s.append(f"BHT*0019*00*{icn}*{_now_ccyymmdd()}*{_now_hhmm()}*CH")
    s.append("NM1*41*2*OPA PLATFORM*****46*OPAPLATFORM")
    s.append("PER*IC*CLAIMS DEPT*TE*5555555555")
    s.append("NM1*40*2*PAYER001*****46*PAYER001")
    s.append("HL*1**20*1")
    s.append(f"NM1*85*2*{provider_name}*****XX*1234567890")
    s.append("N3*123 PROVIDER WAY")
    s.append("N4*ANYTOWN*CA*900010000")
    s.append("REF*EI*123456789")
    s.append("HL*2*1*22*0")
    s.append("SBR*P*18*******CI")
    last = (patient_last or patient).upper()[:35]
    first = (patient_first or "PATIENT").upper()[:25]
    s.append(f"NM1*IL*1*{last}*{first}****MI*W123456789")
    s.append("N3*456 PATIENT ST")
    s.append("N4*ANYTOWN*CA*900020000")
    dob_digits = (ctx.get("dob") or "19000101").replace("-", "")
    s.append(f"DMG*D8*{dob_digits}*U")
    s.append("NM1*PR*2*PAYER001*****PI*PAYER001")
    s.append(
        f"CLM*{ctx['claim_id']}*{billed:.2f}***"
        + ("11:A:1" if is_institutional else "11:B:1")
        + "*Y*A*Y*Y"
    )
    s.append(f"DTP*434*RD8*{dos_ccyymmdd}-{dos_ccyymmdd}")
    if is_institutional and ctx.get("drg"):
        s.append(f"HI*DR:{ctx['drg']}")
    if icd10:
        hi = []
        for i, dx in enumerate(icd10):
            qual = "ABK" if i == 0 else "ABF"
            hi.append(f"{qual}:{dx.replace('.', '')}")
        s.append("HI*" + "*".join(hi))
    for idx, cpt in enumerate(cpts, start=1):
        s.append(f"LX*{idx}")
        line_amount = billed / max(len(cpts), 1)
        if is_institutional:
            s.append(f"SV2**HC:{cpt}*{line_amount:.2f}*UN*1***Y")
        else:
            s.append(f"SV1*HC:{cpt}*{line_amount:.2f}*UN*1***1")
        s.append(f"DTP*472*D8*{dos_ccyymmdd}")
    se_count = len(s) - 2 + 1
    s.append(f"SE*{se_count}*0001")
    s.append(f"GE*1*{icn}")
    s.append(f"IEA*1*{icn}")
    return "~\n".join(s) + "~\n"


# ── Plaintext document builders ──────────────────────────────────────────

def _claim_summary_text(ctx: dict[str, Any]) -> str:
    cpts = ", ".join(ctx.get("cpts") or []) or "none"
    icd10 = ", ".join(ctx.get("icd10") or []) or "none"
    return (
        "CLAIM SUMMARY\n"
        "=============\n"
        f"Claim ID:        {ctx.get('claim_id')}\n"
        f"ICN:             {ctx.get('icn')}\n"
        f"Claim Form:      {ctx.get('claim_form_type')} ({ctx.get('care_setting')})\n"
        f"DRG:             {ctx.get('drg') or 'N/A'}\n"
        f"Patient:         {ctx.get('patient')}\n"
        f"DOB:             {ctx.get('dob') or 'N/A'}\n"
        f"Date of Service: {ctx.get('dos')}\n"
        f"Provider:        {ctx.get('provider')}\n"
        f"Billed Amount:   ${float(ctx.get('billed_amount') or 0):,.2f}\n"
        f"Specialty:       {ctx.get('specialty') or 'N/A'}\n"
        f"Status:          {ctx.get('status') or 'N/A'}\n"
        f"Priority:        {ctx.get('priority') or 'N/A'}\n"
        f"CPT/HCPCS:       {cpts}\n"
        f"ICD-10:          {icd10}\n"
        f"Description:     {ctx.get('description') or 'N/A'}\n"
    )


def _findings_text(findings: List[dict]) -> str:
    if not findings:
        return "No AI findings on file for this claim.\n"
    lines = ["AI FINDINGS", "===========", ""]
    for i, f in enumerate(findings, start=1):
        lines.append(f"[{i}] {(f.get('severity') or '').upper()} — {f.get('title') or ''}")
        lines.append(f.get("body") or "")
        lines.append("")
    return "\n".join(lines)


def _denial_letter(ctx: dict[str, Any], reason: str) -> str:
    today = datetime.utcnow().strftime("%B %d, %Y")
    return (
        f"{today}\n\n"
        f"RE: Notice of Claim Denial\n"
        f"Member: {ctx.get('patient')}\n"
        f"Claim ID: {ctx.get('claim_id')}\n"
        f"Date of Service: {ctx.get('dos')}\n"
        f"Provider: {ctx.get('provider')}\n"
        f"Billed Amount: ${float(ctx.get('billed_amount') or 0):,.2f}\n\n"
        "Dear Member,\n\n"
        "After review of the claim referenced above, we have determined that "
        "payment cannot be issued at this time for the reason(s) stated below.\n\n"
        "REASON FOR DENIAL\n"
        "-----------------\n"
        f"{reason.strip()}\n\n"
        "YOUR APPEAL RIGHTS\n"
        "------------------\n"
        "You or your authorized representative have the right to appeal this "
        "decision. A written request for reconsideration must be filed within "
        "sixty (60) calendar days of the date of this notice, pursuant to 42 CFR "
        "§422.560 and §422.582. Submit appeals in writing to the address on file "
        "and include this notice along with any supporting clinical documentation, "
        "operative reports, or coding rationale you wish to be considered.\n\n"
        "If you have questions, contact Member Services at 1-800-555-0100.\n\n"
        "Sincerely,\n"
        "Claims Review Department\n"
    )


def _approval_review_summary(ctx: dict[str, Any], findings: List[dict]) -> str:
    today = datetime.utcnow().strftime("%B %d, %Y")
    critical = sum(1 for f in findings if (f.get("severity") or "") == "critical")
    warning = sum(1 for f in findings if (f.get("severity") or "") == "warning")
    return (
        "REVIEW SUMMARY\n==============\n"
        f"Reviewed: {today}\n"
        f"Claim: {ctx.get('claim_id')} — {ctx.get('patient')}\n"
        f"Outcome: APPROVED for payment\n"
        f"AI findings: {len(findings)} total ({critical} critical, {warning} warning)\n"
        "All material findings were resolved or judged non-blocking by the reviewer.\n"
    )


# ── Public ZIP builders ──────────────────────────────────────────────────

def generate_denial_zip(
    ctx: dict[str, Any], findings: List[dict], denial_reason: str
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("denial_letter.txt", _denial_letter(ctx, denial_reason))
        z.writestr("ai_findings.txt", _findings_text(findings))
        z.writestr("claim_summary.txt", _claim_summary_text(ctx))
    return buf.getvalue()


def generate_approval_zip(
    ctx: dict[str, Any],
    findings: List[dict],
    documents: List[dict],
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        ext = "837I" if ctx.get("claim_form_type") == "UB-04" else "837P"
        z.writestr(f"x12_transaction.{ext}.txt", generate_x12(ctx))
        z.writestr("review_summary.txt", _approval_review_summary(ctx, findings))
        z.writestr("claim_summary.txt", _claim_summary_text(ctx))
        for d in documents:
            path = d.get("file_path")
            filename = d.get("filename") or "document"
            if path and os.path.exists(path):
                z.write(path, arcname=f"documents/{filename}")
    return buf.getvalue()
