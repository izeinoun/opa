"""Anthropic-backed AI claim audit + structured extraction.

Ported from ClaimGuard's services/ai_service.py and adapted to OPA's
unified model:
  • CPTs come from claim_lines.cpt_code (no JSON-on-claim).
  • ICD-10s come from claim.primary_icd + union of claim_lines.icd_codes.
  • Patient/provider come from members/providers FKs (not strings).
  • Findings are persisted to the unified `findings` table with
    detector_id='CG-BASIC-V1', confidence/overpayment_amount NULL.

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

from ..config import settings
from ..models.claims import Claim, ClaimLine, line_diag_codes
from ..models.reference import EvidenceRequirement, Member, Provider, ProviderOrg
from ..models.workflow import Finding

logger = logging.getLogger(__name__)

# Single source of truth for the model id (settings.llm_model). evidence_scanner
# and document_generation import this MODEL, so they stay in sync automatically.
MODEL = settings.llm_model
AI_DETECTOR_ID = "CG-BASIC-V1"
AI_DETECTOR_VERSION = "1.0.0"
# Distinct ID for targeted evidence-validation findings so they can be
# distinguished from the general AI audit in queries / UI.
EVIDENCE_DETECTOR_ID = "AI-EVIDENCE-V1"
EVIDENCE_DETECTOR_VERSION = "1.0.0"


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
    "direct and specific.\n\n"
    "PROVIDER-FACING OUTPUT. In addition to the detailed payer-side 'body', "
    "each finding MUST include two short fields written for the BILLING "
    "PROVIDER who has to correct the claim — plain, professional, jargon-light, "
    "and actionable:\n"
    "  • 'issue': ONE sentence stating what is wrong, addressed to the provider "
    "(e.g. \"This claim was billed on a CMS-1500 form, but the documentation "
    "describes an inpatient admission.\").\n"
    "  • 'suggestion': ONE sentence telling the provider exactly what to do to "
    "fix it (e.g. \"Resubmit this claim on a UB-04 institutional form.\"). For "
    "'ok' findings where nothing needs to change, set 'suggestion' to a brief "
    "confirmation such as \"No action needed.\".\n"
    "Return ONLY a valid JSON array, no markdown, no explanation outside the "
    "array."
)

EXTRACTION_SYSTEM_PROMPT = (
    "You are a medical claims intake assistant. Given the raw text of a "
    "CMS-1500 or UB-04 claim form, return a JSON object with these exact "
    "keys:\n"
    "  type ('CMS-1500'|'UB-04')\n"
    "  claim_form ('Inpatient'|'Outpatient')\n"
    "  drg (string|null — only for UB-04 inpatient claims)\n"
    "  lines (array of service line objects — one object per service line row "
    "as it appears on the form, in order; each object has: "
    "revenue_code (string|null — UB-04 FL 42 revenue code e.g. '0360'; null "
    "for CMS-1500 lines where it does not apply), "
    "cpt (string — CPT/HCPCS code for this line, including J-codes; extract "
    "exactly as printed even if the form type makes the code inappropriate), "
    "modifiers (array of up to 4 modifier strings, e.g. ['LT','59']; empty "
    "array if none), "
    "units (integer quantity; default 1 if not shown), "
    "charge (number line-level charge in dollars; null if not individually "
    "itemized))\n"
    "  cpts (array of CPT/HCPCS code strings assembled from the lines array, "
    "for backward compatibility — one entry per line in the same order)\n"
    "  icd10 (array of ICD-10-CM diagnosis codes)\n"
    "  provider (string)\n"
    "  patient (string — full name)\n"
    "  dob (string YYYY-MM-DD or null)\n"
    "  member_number (string|null — payer-assigned subscriber/member ID; "
    "Box 1a on CMS-1500, FL 60 on UB-04)\n"
    "  dos (string YYYY-MM-DD)\n"
    "  billed_amount (number, total dollars)\n"
    "  specialty ('Surgical'|'Oncology'|'Inpatient'|'Other')\n"
    "  description (string — one-sentence summary of the encounter based on "
    "diagnosis and procedures)\n"
    "If a field cannot be confidently extracted, use null (for optionals) or "
    "an empty array (for lists). "
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

EVIDENCE_SYSTEM_PROMPT = (
    "You are a clinical-documentation auditor for a payer. Your job is to "
    "validate that the clinical evidence in the chart supports every billed "
    "code on the claim. This is the targeted evidence-validation pass — not "
    "a general audit. For each billed CPT/HCPCS and each ICD-10-CM code, "
    "decide whether the supporting chart text provides the documentation "
    "that CMS / payer policy requires for that code.\n\n"
    "Categories of evidence to look for:\n"
    "  • Medical necessity: does the documentation explain why the service "
    "was needed, with a supporting diagnosis?\n"
    "  • Procedure documentation: for surgical/procedural CPTs, is there an "
    "operative note or procedure note?\n"
    "  • Modifier substantiation: e.g. modifier-25 (significant separately "
    "identifiable E/M) requires a distinct documented E/M service; modifier-59 "
    "(distinct procedural service) requires documented separation.\n"
    "  • DRG / inpatient: for UB-04 inpatient claims, is there an H&P, an "
    "operative report (if surgical), discharge summary, POA-documented "
    "diagnoses?\n"
    "  • High-dollar J-codes: documented drug name, dose, route, units.\n"
    "  • Time-based codes: documented time spent.\n\n"
    "For each billed code, return a finding with one of these severities:\n"
    "  'critical' — required evidence is missing or contradicts the billed code; "
    "this is likely overpayment exposure\n"
    "  'warning'  — evidence is partial, ambiguous, or weakly supports the code\n"
    "  'ok'       — chart adequately documents the code\n\n"
    "If the chart text is empty or absent, return ONE finding: "
    "{severity: 'warning', title: 'No supporting documentation on file', "
    "body: 'Cannot validate evidence — no chart text has been attached to "
    "this claim.', code: null}.\n\n"
    "Be specific. Quote the policy or guideline. Cite the chart text by "
    "phrase when possible. Return ONLY a valid JSON array. Each item: "
    "{severity, title (max 12 words), body (2-4 sentences with citation), "
    "code (the CPT or ICD this validates, or null for global findings)}. "
    "No markdown, no commentary outside the array."
)


IDENTIFIERS_SYSTEM_PROMPT = (
    "You are a clinical-records intake assistant. Given the raw text of a "
    "medical record / clinical document (e.g. progress note, operative "
    "report, discharge summary), extract the patient's payer identifiers and "
    "every date of service mentioned. Return a JSON object with these exact "
    "keys:\n"
    "  member_number (string|null — the health-plan member / subscriber ID if "
    "printed anywhere; null if absent — clinical charts often omit it)\n"
    "  first_name (string|null)\n"
    "  last_name (string|null)\n"
    "  dob (string YYYY-MM-DD or null)\n"
    "  service_dates (array of strings YYYY-MM-DD — EVERY distinct date of "
    "service / encounter / visit / admission / discharge / procedure date "
    "found in the document, in any order; empty array if none)\n"
    "  service_lines (array of objects {\"cpt\": string|null, \"date\": string "
    "YYYY-MM-DD|null} — ONE per billed/performed procedure, pairing each "
    "CPT/HCPCS procedure code to the specific date that procedure was "
    "performed, WHEN the document enumerates coded procedure lines (e.g. a "
    "claim form or an operative report listing coded procedures). Use an empty "
    "array for narrative notes that do not pair a procedure code with its own "
    "date.)\n"
    "Normalize all dates to YYYY-MM-DD. If a field cannot be confidently "
    "extracted use null (or an empty array for service_dates / service_lines). "
    "Return ONLY a valid JSON object. No markdown, no commentary."
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


# ── Rule-prompt execution (generic, used by LLM-augmented detectors) ─────

def _render_template(template: str, variables: dict[str, str]) -> str:
    for k, v in variables.items():
        template = template.replace(f"{{{{{k}}}}}", str(v) if v is not None else "")
    return template


async def run_rule_prompt(
    rule_id: str,
    prompt_type: str,
    variables: dict[str, str],
) -> "dict[str, Any] | None":
    """Render a rule prompt from the cache, call the model, return parsed JSON or None.

    None is returned on any failure (no prompt in cache, no API key, call error,
    parse error) so callers can safely fall back to deterministic behaviour.
    """
    from .rule_prompt_cache import rule_prompt_cache  # lazy to avoid import-time cycle

    prompt = rule_prompt_cache.get(rule_id, prompt_type)
    if prompt is None:
        logger.debug("run_rule_prompt: no active %s/%s prompt in cache", rule_id, prompt_type)
        return None

    try:
        client = _client()
    except RuntimeError as e:
        logger.warning("run_rule_prompt skipped (%s/%s): %s", rule_id, prompt_type, e)
        return None

    rendered = _render_template(prompt.prompt_template, variables)

    try:
        resp = await client.messages.create(
            model=prompt.model,
            max_tokens=1024,
            temperature=prompt.temperature,
            messages=[{"role": "user", "content": rendered}],
        )
    except Exception as e:
        logger.exception("run_rule_prompt Anthropic call failed (%s/%s): %s", rule_id, prompt_type, e)
        return None

    raw = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    try:
        return _extract_json_object(raw)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(
            "run_rule_prompt parse failed (%s/%s): %s — raw=%r",
            rule_id, prompt_type, e, raw[:400],
        )
        return None


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
        raise RuntimeError("AI service is not configured")
    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:
        raise RuntimeError("AI service is unavailable") from e
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
        line_icds.extend(line_diag_codes(ln))
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
        "body: string (2-4 sentences, payer-side detail with citations), "
        "issue: string (ONE sentence stating the problem, addressed to the "
        "billing provider), suggestion: string (ONE sentence telling the "
        "provider how to fix it)}"
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
            issue_summary=(str(item["issue"]) if item.get("issue") else None),
            suggestion=(str(item["suggestion"]) if item.get("suggestion") else None),
            evidence="{}",
            rule_version=None,
            status="active",
        )
        db.add(f)
        findings.append(f)
    await db.commit()
    return findings


# ── Helper: fetch deterministic evidence requirements for billed codes ──

async def _fetch_evidence_requirements(
    db: AsyncSession, ctx: dict[str, Any]
) -> List[EvidenceRequirement]:
    """Pull active evidence_requirements rows that match any billed code on
    this claim (CPT/HCPCS lines, ICDs, DRG). Returned rows are injected into
    the validation prompt so the AI cites concrete policy expectations
    instead of inferring them freeform."""
    codes_to_check: List[tuple[str, str]] = []
    for cpt in (ctx.get("cpts") or []):
        codes_to_check.append(("cpt", cpt))
        codes_to_check.append(("hcpcs", cpt))   # J-codes / HCPCS share the CPT slot
    for icd in (ctx.get("icd10") or []):
        codes_to_check.append(("icd10", icd))
    if ctx.get("drg"):
        codes_to_check.append(("drg", str(ctx["drg"])))
    if not codes_to_check:
        return []

    # SQLAlchemy can't express a composite IN cleanly across dialects; just
    # collect codes per type and OR them.
    by_type: dict[str, list[str]] = {}
    for ct, code in codes_to_check:
        by_type.setdefault(ct, []).append(code)

    from sqlalchemy import or_
    clauses = [
        ((EvidenceRequirement.code_type == ct) & (EvidenceRequirement.code.in_(codes)))
        for ct, codes in by_type.items()
    ]
    if not clauses:
        return []
    stmt = (
        select(EvidenceRequirement)
        .where(EvidenceRequirement.is_active == True)  # noqa: E712
        .where(or_(*clauses))
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


def _format_requirements_for_prompt(reqs: List[EvidenceRequirement]) -> str:
    if not reqs:
        return ""
    lines = ["", "--- REQUIRED EVIDENCE (deterministic rules from payer policy) ---"]
    for r in reqs:
        lines.append(
            f"\n  Code: {r.code_type.upper()} {r.code}  "
            f"(missing → {r.severity_if_missing})\n"
            f"  Policy:   {r.policy_reference}\n"
            f"  Required: {r.required_evidence}"
        )
    lines.append("--- END REQUIRED EVIDENCE ---")
    lines.append(
        "\nWhen producing findings, you MUST address every code listed above. "
        "If the chart provides what the policy requires, mark it 'ok' with a "
        "brief citation of the chart text. If anything required is missing, "
        "mark it as the severity shown above and quote the exact policy text. "
        "You may add additional findings beyond these rules if you spot other "
        "documentation gaps."
    )
    return "\n".join(lines)


# ── Public API: validate_evidence (chart-vs-claim, targeted) ──────────────

class EvidenceValidationError(Exception):
    """Raised when an evidence-validation run can't complete (AI unavailable,
    response truncated, or unparseable). Carries a user-facing message so the
    route can surface a clear reason instead of silently showing 'no results'."""


async def validate_evidence(claim_id: str, db: AsyncSession) -> List[Finding]:
    """Targeted evidence-validation pass on a claim's billed codes vs. the
    chart text in claim.extracted_text. Pipeline-agnostic: works for pre-pay
    and post-pay. Replaces existing AI-EVIDENCE-V1 findings for this claim
    (always reflects the most recent validation run).

    Returns the list of persisted Finding rows (possibly empty when the AI
    genuinely finds nothing to flag). Raises EvidenceValidationError when the
    run can't complete — AI unavailable, response truncated (max_tokens), or
    unparseable — so callers can surface a clear reason instead of an empty list.
    """
    claim_res = await db.execute(select(Claim).where(Claim.claim_id == claim_id))
    claim = claim_res.scalar_one_or_none()
    if claim is None:
        raise ValueError(f"Claim {claim_id} not found")

    try:
        client = _client()
    except RuntimeError as e:
        logger.warning("Evidence validate skipped for %s: %s", claim_id, e)
        raise EvidenceValidationError(
            "AI evidence validation isn't configured on this server (missing API key)."
        ) from e

    ctx = await _assemble_context(claim, db)
    reqs = await _fetch_evidence_requirements(db, ctx)
    requirements_block = _format_requirements_for_prompt(reqs)

    user_message = (
        f"Claim: {ctx['claim_id']}\n"
        f"Form: {ctx['claim_form_type']} ({ctx['care_setting']})\n"
        f"Date of Service: {ctx['dos']}\n"
        f"Provider: {ctx['provider']}\n"
        f"Patient: {ctx['patient']} (DOB {ctx['dob'] or 'unknown'})\n"
        f"DRG: {ctx['drg'] or 'N/A'}\n"
        f"Billed Amount: ${ctx['billed_amount']:,.2f}\n"
        f"Billed CPT/HCPCS: {', '.join(ctx['cpts']) if ctx['cpts'] else '(none)'}\n"
        f"Billed ICD-10: {', '.join(ctx['icd10']) if ctx['icd10'] else '(none)'}\n"
        f"{requirements_block}\n"
        f"\n--- CHART TEXT (attached supporting documentation) ---\n"
        f"{ctx['extracted_text'] or '(no documentation attached)'}\n"
        f"--- END CHART TEXT ---\n\n"
        "Now produce the evidence-validation JSON array. Address every code "
        "in the REQUIRED EVIDENCE section above (mark each ok / warning / "
        "critical with chart and policy citations), plus any other "
        "documentation findings you spot."
    )

    try:
        resp = await client.messages.create(
            model=MODEL,
            # One detailed finding per billed code (severity + title + a multi-
            # sentence body with chart/policy citations) blows past 2048 on a
            # 5-line claim — the JSON gets truncated mid-string and the parse
            # fails, surfacing as "no results". Give it ample room.
            max_tokens=8192,
            system=EVIDENCE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as e:
        logger.exception("Anthropic validate_evidence failed for %s: %s", claim_id, e)
        raise EvidenceValidationError(
            "The AI service is unavailable right now. Please try again in a moment."
        ) from e

    # A max_tokens stop means the JSON was cut off mid-array — don't try to parse
    # a fragment and silently return nothing; tell the user it was truncated.
    if getattr(resp, "stop_reason", None) == "max_tokens":
        logger.error("validate_evidence truncated (max_tokens) for %s", claim_id)
        raise EvidenceValidationError(
            "The evidence analysis was too long and got cut off before it "
            "finished. Please try again."
        )

    text = "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    )
    try:
        items = _extract_json_array(text)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Could not parse evidence output for %s: %s — raw=%r",
                     claim_id, e, text[:400])
        raise EvidenceValidationError(
            "The evidence analysis came back in an unreadable format. Please try again."
        ) from e

    # Replace previous evidence findings on this claim.
    prev = await db.execute(
        select(Finding).where(
            Finding.claim_id == claim_id,
            Finding.detector_id == EVIDENCE_DETECTOR_ID,
        )
    )
    for old in prev.scalars().all():
        await db.delete(old)

    now = datetime.utcnow().isoformat()
    findings: List[Finding] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity", "warning")).lower()
        if severity not in {"critical", "warning", "ok"}:
            severity = "warning"
        code = item.get("code")
        # Evidence JSON: include the code being validated so the UI can group.
        evidence = json.dumps({"code": code}) if code else "{}"
        f = Finding(
            finding_id=str(uuid.uuid4()),
            claim_id=claim_id,
            claim_line_id=None,
            detector_id=EVIDENCE_DETECTOR_ID,
            detector_version=EVIDENCE_DETECTOR_VERSION,
            fired_at=now,
            overpayment_amount=None,
            severity=severity,
            confidence=None,
            title=str(item.get("title", ""))[:200],
            rationale=str(item.get("body", "")),
            evidence=evidence,
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


# ── Public API: extract_patient_identifiers ───────────────────────────────

async def extract_patient_identifiers(text: str) -> dict[str, Any]:
    """Extract member number, name, DOB, and all dates of service from a
    medical-record's raw text. Used by File Intake to match a clinical PDF to
    an existing case.

    Soft-fails: returns a fully-null/empty result (never raises) when the AI
    service is unconfigured or the call/parse fails — the document then lands
    in the unmatched queue rather than blocking the upload.
    """
    empty = {
        "member_number": None, "first_name": None, "last_name": None,
        "dob": None, "service_dates": [], "service_lines": [],
    }
    if not (text or "").strip():
        return empty
    try:
        client = _client()
    except RuntimeError as e:
        logger.warning("extract_patient_identifiers skipped: %s", e)
        return empty
    try:
        resp = await client.messages.create(
            model=MODEL,
            max_tokens=800,
            system=IDENTIFIERS_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": (
                    "Extract the patient identifiers and dates of service from "
                    f"this medical record:\n\n{text[:18000]}"
                ),
            }],
        )
    except Exception as e:
        logger.exception("extract_patient_identifiers call failed: %s", e)
        return empty

    raw = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    try:
        data = _extract_json_object(raw)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("extract_patient_identifiers parse failed: %s — raw=%r", e, raw[:400])
        return empty
    if not isinstance(data, dict):
        return empty
    # Defensive normalization.
    sds = data.get("service_dates") or []
    data["service_dates"] = [str(d) for d in sds if d] if isinstance(sds, list) else []
    sls = data.get("service_lines") or []
    norm_lines: list[dict[str, Any]] = []
    if isinstance(sls, list):
        for it in sls:
            if isinstance(it, dict):
                cpt = it.get("cpt")
                d = it.get("date")
                norm_lines.append({
                    "cpt": str(cpt).strip() if cpt else None,
                    "date": str(d).strip() if d else None,
                })
    data["service_lines"] = norm_lines
    for k in ("member_number", "first_name", "last_name", "dob"):
        data.setdefault(k, None)
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
