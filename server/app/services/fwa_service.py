"""FWA (Fraud / Waste / Abuse) LLM-assisted detectors.

Covers two FWA rules that need clinical-reasoning judgement:

  FWA-04 — Upcoding: E/M level not supported by the diagnosis complexity
           or the documented encounter. Example: 99214 billed for a routine
           BP recheck.
  FWA-07 — Diagnosis inflation: ICD-10 codes added to the claim that aren't
           supported by the clinical narrative. Example: claim lists DM with
           complications but the chart only mentions controlled DM.

Persists findings into the unified `findings` table with detector_id =
'FWA-04' / 'FWA-07' and fwa_indicator=True / fwa_rule_code set, so SIU and
the case views can surface them via the existing finding pipeline.

Used by BOTH pipelines:
  - ClaimGuard pre-pay calls fwa_service.run() right after ai_service.analyze_claim
  - PayGuard post-pay calls fwa_service.run() right after the detector orchestrator
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

from ..models.claims import Claim, ClaimLine, line_diag_codes
from ..models.reference import Member, Provider, ProviderOrg
from ..models.workflow import CaseFinding, Finding, OpaCase


logger = logging.getLogger(__name__)

# Single source of truth — settings.llm_model (env LLM_MODEL / CLAIMGUARD_MODEL).
# (The old hardcoded "claude-sonnet-4-20250514" 404'd and silently killed the pass.)
from ..config import settings
MODEL = settings.llm_model

# detector_id values used for the FWA findings
DET_UPCODING            = "FWA-04"
DET_DIAGNOSIS_INFLATION = "FWA-07"

_SYSTEM_PROMPT = """You are a payment-integrity reviewer screening claims for two specific fraud / waste / abuse patterns. Be precise. Only fire findings when there is clear evidence in the data provided.

FWA-04 — UPCODING (E/M level not supported by complexity)
The most common upcoding signal: high-level E/M codes (CPT 99204/99205 new patient, 99214/99215 established patient, 99223 inpatient high, 99284/99285 ED high) billed for clinical scenarios that don't warrant them. High-level E/M requires:
  - 99214/99204: moderate complexity — multiple chronic conditions managed, prescription drug management, or new problem with uncertain prognosis
  - 99215/99205: high complexity — multiple/severe acute or chronic conditions, life-threatening symptoms, or extensive data review
  - 99223 (initial hospital high): severe condition, high risk
  - 99285 (ED high): high-severity threat to life or limb
Be conservative. A patient with a single chronic, stable condition and a simple problem typically does NOT support 99214+.

FWA-07 — DIAGNOSIS INFLATION (ICDs not supported by the narrative)
Look for ICD-10 codes on the claim that are NOT supported by the clinical narrative. Common patterns:
  - Adding "with complications" subcodes when the chart shows none (e.g. E11.65 hypoglycemia listed but no documented hypoglycemic episodes).
  - Adding severity modifiers (acute vs unspecified) not in the chart.
  - Listing conditions the chart never mentions (e.g. CHF added but the chart never mentions cardiac history).
  - Listing the maximum number of diagnosis codes the claim allows when the chart only supports 1-2.
DO NOT flag a code as inflated simply because it's not deeply elaborated in the narrative. Only flag when the chart contradicts it or makes no mention of the supporting clinical facts.

Return ONLY a JSON object:
{
  "fwa_04_upcoding": [
    {
      "severity": "critical" | "warning" | "ok",
      "title": "<short label, max 12 words>",
      "rationale": "<2-3 sentences citing what's billed and what the chart shows>",
      "cpts": ["<codes triggering the finding>"]
    }
  ],
  "fwa_07_diagnosis_inflation": [
    {
      "severity": "critical" | "warning" | "ok",
      "title": "<short label, max 12 words>",
      "rationale": "<2-3 sentences citing the unsupported ICD and what's missing>",
      "icd10": ["<codes triggering the finding>"]
    }
  ]
}

Rules:
- Use 'critical' when you'd recommend denial / SIU escalation.
- Use 'warning' when the pattern is suspicious but reasonably defensible.
- Use 'ok' (or empty array) when no upcoding / inflation signal is present.
- If a category has no findings, return an empty array — do not invent findings.
- No commentary, no markdown — just the JSON object."""


def _client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("AI service is not configured")
    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:
        raise RuntimeError("AI service is unavailable") from e
    return AsyncAnthropic(api_key=api_key)


async def _assemble_context(claim: Claim, db: AsyncSession) -> dict[str, Any]:
    """Pull what the FWA prompt needs: codes, member age, provider specialty,
    billed totals, claim form, and any clinical narrative we have."""
    lines_res = await db.execute(
        select(ClaimLine).where(ClaimLine.claim_id == claim.claim_id)
    )
    lines = list(lines_res.scalars().all())
    cpts = [ln.cpt_code for ln in lines if ln.cpt_code]

    line_icds: List[str] = []
    for ln in lines:
        line_icds.extend(line_diag_codes(ln))
    icd_set = set()
    icd10: List[str] = []
    for code in [claim.primary_icd, *line_icds]:
        if code and code not in icd_set:
            icd10.append(code)
            icd_set.add(code)

    # Patient age (best-effort; some scenarios don't store DOB on the claim)
    age: Optional[int] = None
    member = (await db.execute(
        select(Member).where(Member.member_id == claim.member_id)
    )).scalar_one_or_none()
    if member and member.date_of_birth:
        try:
            from datetime import date
            dob = date.fromisoformat(member.date_of_birth[:10])
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        except Exception:
            pass

    # Provider specialty (rendering, fallback billing)
    provider_specialty: Optional[str] = None
    npi = claim.rendering_provider_npi or claim.billing_provider_npi
    if npi:
        prov = (await db.execute(
            select(Provider).where(Provider.npi == npi)
        )).scalar_one_or_none()
        if prov:
            provider_specialty = prov.specialty

    # Clinical narrative — pre-pay has claim.extracted_text + claim_summary;
    # post-pay typically has nothing. Pass whatever we have.
    chart_text = ((claim.extracted_text or "") + "\n" + (claim.claim_summary or "")).strip()
    if len(chart_text) > 30_000:
        chart_text = chart_text[:30_000] + "\n[...truncated]"

    return {
        "cpts":               cpts,
        "icd10":              icd10,
        "primary_icd":        claim.primary_icd,
        "drg":                claim.drg,
        "claim_form_type":    claim.claim_form_type,
        "care_setting":       claim.care_setting,
        "pos_code":           claim.pos_code,
        "billed_amount":      float(claim.total_billed or 0),
        "patient_age":        age,
        "provider_specialty": provider_specialty,
        "pipeline_mode":      claim.pipeline_mode,
        "chart_text":         chart_text,
    }


def _build_user_prompt(ctx: dict[str, Any]) -> str:
    chart_block = (
        ctx["chart_text"] if ctx["chart_text"]
        else "(no chart text on file — base your FWA-07 judgement on the claim "
             "metadata alone; be appropriately conservative)"
    )
    return f"""CLAIM SNAPSHOT:
- Pipeline:          {ctx['pipeline_mode']}
- Form type:         {ctx.get('claim_form_type') or 'unknown'}
- Care setting:      {ctx.get('care_setting') or 'unknown'}
- DRG:               {ctx.get('drg') or 'n/a'}
- Place of service:  {ctx.get('pos_code') or 'unknown'}
- Total billed:      ${ctx['billed_amount']:.2f}
- Patient age:       {ctx['patient_age'] if ctx['patient_age'] is not None else 'unknown'}
- Provider specialty:{ctx['provider_specialty'] or 'unknown'}

BILLED CPTs/HCPCS:   {', '.join(ctx['cpts']) or '(none)'}
ICD-10 DIAGNOSES:    {', '.join(ctx['icd10']) or '(none)'}
PRIMARY ICD:         {ctx.get('primary_icd') or '(none)'}

CHART / NARRATIVE:
{chart_block}

Run FWA-04 (upcoding) and FWA-07 (diagnosis inflation) checks per the system prompt. Return the JSON object."""


def _parse(raw: str) -> dict[str, Any]:
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        raise ValueError("No JSON object in FWA response")
    blob = m.group(0)
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        cleaned = re.sub(r",(\s*[\]}])", r"\1", blob)
        return json.loads(cleaned)


_VALID_SEVERITY = {"critical", "warning", "ok"}


async def _link_to_case(db: AsyncSession, claim_id: str, finding: Finding) -> None:
    """Create a CaseFinding link if a case exists for this claim. PayGuard
    pulls findings via the case_findings join, so post-pay findings need
    this. Pre-pay reads by claim_id and doesn't need the link, but adding
    it is harmless and keeps post-promotion (pre→post) consistent."""
    case = (await db.execute(
        select(OpaCase).where(OpaCase.claim_id == claim_id).limit(1)
    )).scalar_one_or_none()
    if case is None:
        return
    db.add(CaseFinding(case_id=case.case_id, finding_id=finding.finding_id))


def _persist_findings(
    db: AsyncSession,
    *,
    claim_id: str,
    detector_id: str,
    fwa_rule_code: str,
    items: list,
    extra_field: str,   # 'cpts' or 'icd10' — the prompt's code-list key
) -> List[Finding]:
    out: List[Finding] = []
    now = datetime.utcnow().isoformat()
    for item in items:
        if not isinstance(item, dict):
            continue
        sev = str(item.get("severity") or "warning").lower()
        if sev not in _VALID_SEVERITY:
            sev = "warning"
        # Skip 'ok' findings — they're not actionable signals; we only
        # persist material concerns (critical / warning).
        if sev == "ok":
            continue
        title = str(item.get("title") or "")[:200]
        rationale = str(item.get("rationale") or "").strip() or "(no rationale)"
        evidence = {extra_field: item.get(extra_field) or []}
        f = Finding(
            finding_id=str(uuid.uuid4()),
            claim_id=claim_id,
            claim_line_id=None,
            detector_id=detector_id,
            detector_version="1.0.0",
            fired_at=now,
            overpayment_amount=None,
            severity=sev,
            confidence=None,
            title=title,
            rationale=rationale,
            evidence=json.dumps(evidence),
            rule_version=None,
            status="active",
            fwa_indicator=True,
            fwa_rule_code=fwa_rule_code,
        )
        db.add(f)
        out.append(f)
    return out


async def run(claim_id: str, db: AsyncSession) -> List[Finding]:
    """Run FWA-04 + FWA-07 against the claim. Replaces any prior FWA-04 /
    FWA-07 findings for this claim so re-runs converge.

    Fails soft: if the API key is missing or Claude returns garbage, logs and
    returns []. Callers should never see this raise — these are advisory
    signals on top of the deterministic detectors.
    """
    claim = (await db.execute(
        select(Claim).where(Claim.claim_id == claim_id)
    )).scalar_one_or_none()
    if claim is None:
        return []

    # Delete previous FWA-04 / FWA-07 findings to keep the row count stable
    # across re-runs.
    prev = (await db.execute(
        select(Finding).where(
            Finding.claim_id == claim_id,
            Finding.detector_id.in_((DET_UPCODING, DET_DIAGNOSIS_INFLATION)),
        )
    )).scalars().all()
    for p in prev:
        await db.delete(p)

    try:
        ctx = await _assemble_context(claim, db)
        client = _client()
        resp = await client.messages.create(
            model=MODEL,
            max_tokens=2_000,
            temperature=0,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_prompt(ctx)}],
        )
        raw = resp.content[0].text if resp.content else ""
        data = _parse(raw)
    except RuntimeError as e:
        # No API key / SDK missing — common in dev; don't crash the analyze flow.
        logger.warning("FWA LLM skipped for %s: %s", claim_id, e)
        return []
    except Exception as e:
        logger.exception("FWA LLM failed for %s: %s", claim_id, e)
        return []

    findings: List[Finding] = []
    findings.extend(_persist_findings(
        db,
        claim_id=claim_id,
        detector_id=DET_UPCODING,
        fwa_rule_code="FWA-04",
        items=data.get("fwa_04_upcoding") or [],
        extra_field="cpts",
    ))
    findings.extend(_persist_findings(
        db,
        claim_id=claim_id,
        detector_id=DET_DIAGNOSIS_INFLATION,
        fwa_rule_code="FWA-07",
        items=data.get("fwa_07_diagnosis_inflation") or [],
        extra_field="icd10",
    ))
    await db.flush()
    # Link to case if one exists — post-pay reads via case_findings.
    for f in findings:
        await _link_to_case(db, claim_id, f)
    await db.flush()
    return findings
