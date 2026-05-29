"""Anthropic-backed AI claim audit + structured extraction.

Ported from ClaimGuard's services/ai_service.py and adapted to OPA's
unified model:
  • CPTs come from claim_lines.cpt_code (no JSON-on-claim).
  • ICD-10s come from claim.primary_icd + union of claim_lines.icd_codes.
  • Patient/provider come from members/providers FKs (not strings).
  • Findings are persisted to the unified `findings` table with
    detector_id='AI-CLAUDE-V1', confidence/overpayment_amount NULL.

Public API:
    analyze_claim(claim_id, db) -> list[Finding]
    extract_claim_from_text(pdf_text) -> dict
    generate_claim_summary(claim_id, db) -> str
    generate_code_descriptions(icd10_codes, cpt_codes) -> dict
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.claims import Claim, ClaimLine
from ..models.reference import Member, Provider, ProviderOrg
from ..models.workflow import Finding

logger = logging.getLogger(__name__)

MODEL = os.getenv("CLAIMGUARD_MODEL", "claude-sonnet-4-20250514")
AI_DETECTOR_ID = "AI-CLAUDE-V1"
AI_DETECTOR_VERSION = "1.0.0"


# ── Prompts (verbatim from ClaimGuard) ────────────────────────────────────

ANALYZE_SYSTEM_PROMPT = (
    "You are a senior medical coding auditor and clinical documentation specialist "
    "with expertise in ICD-10-CM, CPT, HCPCS Level II, DRG grouping (MS-DRG v41), "
    "NCCI edits, CMS Medicare coverage policies, and commercial payer LCD/NCD "
    "guidelines. You are reviewing a high-dollar inpatient or outpatient claim on "
    "behalf of a payer prior to payment.\n\n"
    "AUTHORITATIVE BILLED DATA. The fields 'CPT/HCPCS Codes' and 'ICD-10 Diagnosis "
    "Codes' in the user message are the ONLY codes actually billed on the claim. "
    "The 'Extracted Document Text' field is supporting clinical documentation, "
    "which may mention diagnoses, procedures, or codes that are NOT on the claim. "
    "Never assume a code mentioned only in the document text is billed.\n\n"
    "FORM-TYPE RULES. UB-04 institutional inpatient claims are paid by DRG and "
    "should not list CPT/HCPCS in service lines (inpatient procedures belong in "
    "ICD-10-PCS, not on this form). UB-04 outpatient and CMS-1500 claims do use "
    "CPT/HCPCS. POA indicators apply ONLY to UB-04 claims and ONLY to the "
    "diagnosis codes actually billed on the claim — not to codes mentioned in "
    "the chart.\n\n"
    "Your goal is to identify: (1) coding errors including wrong modifiers, "
    "unbundling, upcoding, incorrect DRG assignment, J-code quantity mismatches, "
    "and diagnosis sequencing violations per ICD-10-CM Official Guidelines; "
    "(2) medical necessity gaps where the submitted diagnosis codes do not "
    "support the procedures billed or where documentation requirements are not "
    "met; (3) NCCI edit conflicts between procedure codes; (4) missing or "
    "incorrect POA indicators on UB-04 claims (only for billed diagnoses); "
    "(5) chart-vs-claim discrepancies where the supporting documentation "
    "describes diagnoses or procedures that are NOT reflected on the claim — "
    "label these explicitly as 'Documented but not billed' rather than as POA "
    "issues. For each finding, cite the specific guideline, edit, or policy. "
    "Quantify financial impact where possible (e.g. DRG downgrade = -$X). Be "
    "direct and specific. Return ONLY a valid JSON array, no markdown, no "
    "explanation outside the array."
)

EXTRACTION_SYSTEM_PROMPT = (
    "You are a medical claims intake assistant. Given the raw text of a "
    "CMS-1500 or UB-04 claim form, return a JSON object with these exact "
    "keys: type ('CMS-1500'|'UB-04'), claim_form ('Inpatient'|'Outpatient'), "
    "drg (string|null — only for UB-04 inpatient claims), cpts (array of "
    "strings — CPT/HCPCS codes including J-codes), icd10 (array of ICD-10-CM "
    "diagnosis codes), provider (string), patient (string — full name), dob "
    "(string YYYY-MM-DD or null), dos (string YYYY-MM-DD), billed_amount "
    "(number, dollars), specialty ('Surgical'|'Oncology'|'Inpatient'|"
    "'Other'), description (string — one-sentence summary of the encounter "
    "based on diagnosis and procedures). If a field cannot be confidently "
    "extracted, use null (for optionals) or an empty array (for lists). "
    "Return ONLY a valid JSON object. No markdown, no commentary."
)

SUMMARY_SYSTEM_PROMPT = (
    "You are a medical claims analyst writing a brief, neutral summary of a "
    "claim for a payer-side reviewer who needs to come up to speed in under "
    "ten seconds. Cover, in 2-3 sentences and plain English: (1) who the "
    "patient is and the clinical picture, (2) what was done / billed and on "
    "what form, (3) any obviously notable feature of the billing (high "
    "dollar amount, unusual codes, DRG class). Be factual. Do not opine on "
    "approval or denial. Do not list every code. No headers, no bullet "
    "points, no markdown — just prose."
)

CODE_DESCRIPTIONS_SYSTEM_PROMPT = (
    "You are an authoritative reference for ICD-10-CM diagnosis codes, CPT "
    "procedure codes, and HCPCS Level II codes. Given a list of codes, return "
    "a JSON object mapping each code (exactly as given) to its official "
    "short description. Use the standard CMS/AMA wording, kept to one line "
    "(typically 6-15 words). If a code is invalid or unrecognized, map it to "
    "the string 'Unknown code'. Do not editorialize. Do not add any field "
    "other than the code mapping. Return ONLY a valid JSON object, no "
    "markdown, no commentary."
)


# ── JSON parsing helpers ──────────────────────────────────────────────────

def _extract_json_array(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if not m:
            raise
        data = json.loads(m.group(0))
    if not isinstance(data, list):
        raise ValueError("Model did not return a JSON array")
    return data


def _extract_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise
        return json.loads(m.group(0))


# ── Anthropic client factory ──────────────────────────────────────────────

def _client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:
        raise RuntimeError("anthropic SDK not installed") from e
    return AsyncAnthropic(api_key=api_key)


# ── Context assembly (model adapter) ──────────────────────────────────────

async def _assemble_context(claim: Claim, db: AsyncSession) -> dict[str, Any]:
    """Pull the data points the prompts expect from our normalized model."""
    # Lines (CPTs + per-line ICDs)
    lines_res = await db.execute(
        select(ClaimLine).where(ClaimLine.claim_id == claim.claim_id)
    )
    lines = list(lines_res.scalars().all())
    cpts = [ln.cpt_code for ln in lines if ln.cpt_code]
    line_icds: List[str] = []
    for ln in lines:
        if not ln.icd_codes:
            continue
        try:
            arr = json.loads(ln.icd_codes)
            line_icds.extend([c for c in arr if c])
        except Exception:
            pass
    icd10 = []
    seen_icd = set()
    for code in [claim.primary_icd, *line_icds]:
        if code and code not in seen_icd:
            icd10.append(code)
            seen_icd.add(code)

    # Member → patient name + DOB
    member_res = await db.execute(
        select(Member).where(Member.member_id == claim.member_id)
    )
    member = member_res.scalar_one_or_none()
    patient_name = (
        f"{member.first_name} {member.last_name}" if member else "Unknown Patient"
    )
    dob = member.date_of_birth if member else None

    # Provider org → provider name
    org_res = await db.execute(
        select(ProviderOrg).where(ProviderOrg.provider_org_id == claim.provider_org_id)
    )
    org = org_res.scalar_one_or_none()
    provider_name = org.name if org else "Unknown Provider"

    return {
        "claim_id": claim.icn or claim.claim_id,
        "claim_form_type": claim.claim_form_type or "CMS-1500",
        "care_setting": claim.care_setting or "Outpatient",
        "dos": claim.service_from_date,
        "billed_amount": float(claim.total_billed or 0),
        "provider": provider_name,
        "patient": patient_name,
        "dob": dob,
        "drg": claim.drg,
        "cpts": cpts,
        "icd10": icd10,
        "description": claim.description,
        "extracted_text": claim.extracted_text,
    }


def _build_analyze_user_msg(ctx: dict) -> str:
    return (
        f"Review this claim:\n"
        f"Claim ID: {ctx['claim_id']}\n"
        f"Claim Type: {ctx['claim_form_type']} ({ctx['care_setting']})\n"
        f"Date of Service: {ctx['dos']}\n"
        f"Billed Amount: ${ctx['billed_amount']:,.2f}\n"
        f"Provider: {ctx['provider']}\n"
        f"Patient DOB: {ctx['dob'] or 'N/A'}\n"
        f"DRG: {ctx['drg'] or 'N/A'}\n"
        f"CPT/HCPCS Codes: {', '.join(ctx['cpts']) if ctx['cpts'] else 'none'}\n"
        f"ICD-10 Diagnosis Codes: {', '.join(ctx['icd10']) if ctx['icd10'] else 'none'}\n"
        f"Clinical Description: {ctx['description'] or 'N/A'}\n"
        f"Extracted Document Text: {ctx['extracted_text'] or 'No documents uploaded'}\n\n"
        "Return a JSON array of findings. Each finding: "
        "{severity: 'critical'|'warning'|'ok', title: string (max 10 words), "
        "body: string (2-4 sentences, specific and actionable)}"
    )


# ── Public API: analyze_claim ─────────────────────────────────────────────

async def analyze_claim(claim_id: str, db: AsyncSession) -> List[Finding]:
    """Run AI audit on a claim and persist findings to the unified `findings`
    table. Existing AI findings for this claim are deleted first (matches
    ClaimGuard's 'always reflect most recent run' semantics).

    Returns the list of persisted Finding rows.
    """
    claim_res = await db.execute(select(Claim).where(Claim.claim_id == claim_id))
    claim = claim_res.scalar_one_or_none()
    if claim is None:
        raise ValueError(f"Claim {claim_id} not found")

    try:
        client = _client()
    except RuntimeError as e:
        logger.warning("AI analyze skipped for %s: %s", claim_id, e)
        return []

    ctx = await _assemble_context(claim, db)
    user_message = _build_analyze_user_msg(ctx)

    try:
        resp = await client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=ANALYZE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as e:
        logger.exception("Anthropic analyze call failed for %s: %s", claim_id, e)
        return []

    text = "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    )
    try:
        items = _extract_json_array(text)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Could not parse model output for %s: %s — raw=%r", claim_id, e, text[:400])
        return []

    # Delete previous AI findings for this claim — matches ClaimGuard semantics.
    prev_res = await db.execute(
        select(Finding).where(
            Finding.claim_id == claim_id,
            Finding.detector_id == AI_DETECTOR_ID,
        )
    )
    for old in prev_res.scalars().all():
        await db.delete(old)

    now = datetime.utcnow().isoformat()
    findings: List[Finding] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity", "warning")).lower()
        if severity not in {"critical", "warning", "ok"}:
            severity = "warning"
        f = Finding(
            finding_id=str(uuid.uuid4()),
            claim_id=claim_id,
            claim_line_id=None,
            detector_id=AI_DETECTOR_ID,
            detector_version=AI_DETECTOR_VERSION,
            fired_at=now,
            overpayment_amount=None,
            severity=severity,
            confidence=None,
            title=str(item.get("title", ""))[:200],
            rationale=str(item.get("body", "")),
            evidence="{}",
            rule_version=None,
            status="active",
        )
        db.add(f)
        findings.append(f)
    await db.commit()
    return findings


# ── Public API: extract_claim_from_text ───────────────────────────────────

async def extract_claim_from_text(pdf_text: str) -> dict[str, Any]:
    """Send raw PDF text to Claude; return a structured claim dict.

    Raises RuntimeError on hard failure (no key, SDK missing, empty input,
    parse error). Caller should catch and surface a friendly error.
    """
    if not pdf_text.strip():
        raise RuntimeError("PDF contained no extractable text")
    client = _client()
    resp = await client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=EXTRACTION_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract the claim from this CMS-1500 or UB-04 text:\n\n"
                    f"{pdf_text[:18000]}"
                ),
            }
        ],
    )
    text = "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    )
    data = _extract_json_object(text)
    if not isinstance(data, dict):
        raise RuntimeError("Model did not return a JSON object")
    return data


# ── Public API: generate_claim_summary ────────────────────────────────────

async def generate_claim_summary(claim_id: str, db: AsyncSession) -> str:
    claim_res = await db.execute(select(Claim).where(Claim.claim_id == claim_id))
    claim = claim_res.scalar_one_or_none()
    if claim is None:
        raise ValueError(f"Claim {claim_id} not found")

    client = _client()
    ctx = await _assemble_context(claim, db)
    user_msg = (
        f"Claim {ctx['claim_id']} — {ctx['claim_form_type']} {ctx['care_setting']}\n"
        f"Patient: {ctx['patient']} (DOB {ctx['dob'] or 'unknown'})\n"
        f"Provider: {ctx['provider']}\n"
        f"Date of Service: {ctx['dos']}\n"
        f"DRG: {ctx['drg'] or 'N/A'}\n"
        f"CPT/HCPCS: {', '.join(ctx['cpts']) if ctx['cpts'] else 'none'}\n"
        f"ICD-10: {', '.join(ctx['icd10']) if ctx['icd10'] else 'none'}\n"
        f"Billed: ${ctx['billed_amount']:,.2f}\n"
        f"Description: {ctx['description'] or '(none)'}\n"
        "\nWrite the 2-3 sentence summary now."
    )
    resp = await client.messages.create(
        model=MODEL,
        max_tokens=400,
        system=SUMMARY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip()
    if not text:
        raise RuntimeError("Model returned empty summary")
    return text


# ── Public API: generate_code_descriptions ────────────────────────────────

async def generate_code_descriptions(
    icd10_codes: list[str], cpt_codes: list[str]
) -> dict[str, str]:
    seen: list[str] = []
    for c in [*icd10_codes, *cpt_codes]:
        if c and c not in seen:
            seen.append(c)
    if not seen:
        return {}

    client = _client()
    user_msg = (
        f"ICD-10-CM codes: {', '.join(icd10_codes) if icd10_codes else '(none)'}\n"
        f"CPT/HCPCS codes: {', '.join(cpt_codes) if cpt_codes else '(none)'}\n\n"
        "Return the JSON mapping now."
    )
    resp = await client.messages.create(
        model=MODEL,
        max_tokens=800,
        system=CODE_DESCRIPTIONS_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    )
    data = _extract_json_object(text)
    if not isinstance(data, dict):
        raise RuntimeError("Model did not return a JSON object")
    for c in seen:
        if c not in data:
            data[c] = "Unknown code"
    return {str(k): str(v) for k, v in data.items()}
