"""DET-19: E/M Upcoding Detector.

Flags high-level Evaluation & Management (E/M) codes when the claim's
documented diagnoses do not support the billed complexity level.

This rule is LLM-only — deterministic lookup cannot reason about MDM
(Medical Decision Making) complexity. If no evaluation prompt is loaded
in the cache the detector returns no findings and logs a warning.

Covered E/M families (level 4-5 only to avoid noise):
  Office/outpatient new patient:        99204, 99205
  Office/outpatient established:        99214, 99215
  Hospital inpatient initial:           99223
  Hospital inpatient subsequent:        99233
  Emergency department:                 99284, 99285
  Hospital observation:                 99235, 99236
"""
import json
import logging
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim, line_diag_codes
from ..services.rule_prompt_cache import rule_prompt_cache

logger = logging.getLogger(__name__)

# High-level E/M codes worth evaluating for upcoding.
# Level 4-5 for outpatient; highest tier for inpatient / ED / observation.
HIGH_LEVEL_EM: set[str] = {
    "99204", "99205",   # office new patient
    "99214", "99215",   # office established
    "99223",            # inpatient initial — high complexity
    "99233",            # inpatient subsequent — high complexity
    "99284", "99285",   # emergency department
    "99235", "99236",   # hospital observation
}

# Maps each high-level E/M code to the one-level-down alternative.
# Used to frame the "what level is supported?" guidance in findings.
EM_STEP_DOWN: dict[str, str] = {
    "99205": "99204", "99204": "99203",
    "99215": "99214", "99214": "99213",
    "99223": "99222",
    "99233": "99232",
    "99285": "99284", "99284": "99283",
    "99236": "99235", "99235": "99234",
}


def _format_lines(lines) -> str:
    parts = []
    for ln in lines:
        if not ln.cpt_code:
            continue
        mods = f" [{ln.modifier}]" if getattr(ln, "modifier", None) else ""
        icds = line_diag_codes(ln)
        dx = f" | DX: {', '.join(icds)}" if icds else ""
        parts.append(f"- CPT {ln.cpt_code}{mods} x{ln.units_billed}{dx}")
    return "\n".join(parts) or "(no lines)"


def _substitute(template: str, ctx: dict) -> str:
    result = template
    for key, val in ctx.items():
        result = result.replace("{{" + key + "}}", str(val))
    return result


async def _call_llm(prompt_text: str, model: str, temperature: float) -> dict:
    from ..services.ai_service import _client
    client = _client()
    resp = await client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt_text}],
    )
    raw = resp.content[0].text.strip()
    # Strip markdown code fences if model wraps the JSON
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


class UpcodingDetector(BaseDetector):
    code = "DET-19"
    name = "E/M Upcoding Detector"
    fwa_rule_code = "FWA-01"   # upcoding is a fraud/waste signal

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        results: List[DetectorResult] = []
        lines = claim.lines or []

        # Collect high-level E/M codes present on the claim.
        em_lines = [ln for ln in lines if ln.cpt_code in HIGH_LEVEL_EM]
        if not em_lines:
            return results

        # Collect all ICD codes.
        all_icds: list[str] = []
        if claim.primary_icd and claim.primary_icd.strip():
            all_icds.append(claim.primary_icd.strip())
        for ln in lines:
            for code in line_diag_codes(ln):
                if code not in all_icds:
                    all_icds.append(code)

        other_icds = [c for c in all_icds if c != (claim.primary_icd or "").strip()]

        # Load evaluation prompt — if absent, cannot evaluate.
        eval_prompt = rule_prompt_cache.get_evaluation(self.code)
        if not eval_prompt:
            logger.warning(
                "[DET-19] No active evaluation prompt in cache — upcoding check skipped "
                "(claim %s). Add a prompt via Admin → Rule Prompts.",
                claim.claim_id,
            )
            return results

        ctx = {
            "em_codes": ", ".join(sorted({ln.cpt_code for ln in em_lines})),
            "primary_icd": claim.primary_icd or "N/A",
            "other_icd_codes": ", ".join(other_icds) if other_icds else "none",
            "pos_code": getattr(claim, "pos_code", "N/A"),
            "claim_lines": _format_lines(lines),
        }

        try:
            filled = _substitute(eval_prompt.prompt_template, ctx)
            llm_resp = await _call_llm(filled, eval_prompt.model, eval_prompt.temperature)
        except Exception as exc:
            logger.error("[DET-19] LLM evaluation failed (claim %s): %s", claim.claim_id, exc)
            return results

        for finding in llm_resp.get("findings", []):
            if not finding.get("upcoding_detected"):
                continue

            billed = finding.get("billed_code", "?")
            supported = finding.get("max_supported_level", EM_STEP_DOWN.get(billed, "lower level"))
            confidence = float(finding.get("confidence", 0.5))

            # Approximate overpayment: difference between billed line and supported level.
            affected_lines = [ln for ln in em_lines if ln.cpt_code == billed]
            overpayment = round(sum(
                (ln.paid_amount or 0.0) * 0.30   # conservative ~30% rate differential
                for ln in affected_lines
            ), 2)

            results.append(DetectorResult(
                detector_code=self.code,
                finding_type="EM_UPCODING",
                description=(
                    f"E/M code {billed} billed but diagnoses support at most {supported}. "
                    f"{finding.get('rationale', '')}"
                ),
                overpayment_amount=overpayment,
                confidence_score=min(confidence, 0.90),
                evidence={
                    "billed_code": billed,
                    "max_supported_level": supported,
                    "supporting_diagnoses": finding.get("supporting_diagnoses", []),
                    "rationale": finding.get("rationale", ""),
                    "llm_confidence": confidence,
                    "affected_line_ids": [ln.claim_line_id for ln in affected_lines],
                },
            ))

        return results
