import json
import logging
from typing import List, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim, line_diag_codes
from ..models.reference import CptDxCoverage
from ..services.rule_prompt_cache import rule_prompt_cache

logger = logging.getLogger(__name__)

# Bundling rules stay hardcoded — comprehensive→component relationships are
# defined by NCCI policy and don't map naturally to the CPT-DX coverage table.
BUNDLED_CODES = {
    "27447": ["27310", "27370", "27372"],
    "43239": ["43235", "43236"],
    "93306": ["93307", "93308"],
    "99215": ["99212", "99213", "99214"],
    "70553": ["70551", "70552"],
}


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
        max_tokens=2048,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt_text}],
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


class CodingErrorDetector(BaseDetector):
    code = "DET-09"
    name = "Coding/Documentation Error Detector"

    async def _evaluate_ub04_cpts(self, claim, cpt_lines) -> DetectorResult:
        """Call the LLM evaluation prompt for CPT_ON_INPATIENT_UB04; fall back to
        deterministic finding when no prompt is loaded or the LLM call fails."""
        codes_str = ", ".join(sorted({l.cpt_code for l in cpt_lines}))
        affected_ids = [l.claim_line_id for l in cpt_lines]
        overpayment = round(sum(l.paid_amount or 0.0 for l in cpt_lines), 2)

        def _deterministic() -> DetectorResult:
            return DetectorResult(
                detector_code=self.code,
                finding_type="CPT_ON_INPATIENT_UB04",
                description=(
                    f"CPT/HCPCS code(s) {codes_str} billed on a UB-04 inpatient claim. "
                    f"Inpatient facility claims are DRG-based; procedures must be coded "
                    f"in ICD-10-PCS, not CPT. CMS-1450 FL 44 should carry revenue codes, not CPT."
                ),
                overpayment_amount=overpayment,
                confidence_score=0.95,
                evidence={
                    "cpt_codes": sorted({l.cpt_code for l in cpt_lines}),
                    "affected_line_ids": affected_ids,
                },
            )

        eval_prompt = rule_prompt_cache.get_evaluation(self.code)
        if not eval_prompt:
            logger.warning(
                "[DET-09] No active evaluation prompt — using deterministic finding (claim %s).",
                claim.claim_id,
            )
            return _deterministic()

        flagged = [
            {
                "code": l.cpt_code,
                "code_type": "HCPCS" if l.cpt_code.startswith(tuple("ABCDEFGHJKLMNPQRSTUV")) else "CPT",
                "revenue_code": getattr(l, "revenue_code", None) or "N/A",
                "revenue_description": "N/A",
                "units": getattr(l, "units_billed", 1),
                "charge": getattr(l, "billed_amount", 0.0),
            }
            for l in cpt_lines
        ]

        ctx = {
            "claim_form_type": getattr(claim, "claim_form_type", "UB-04"),
            "care_setting": getattr(claim, "care_setting", "Inpatient"),
            "drg": getattr(claim, "drg", "N/A") or "N/A",
            "dos": getattr(claim, "service_date_from", None) or getattr(claim, "dos", "N/A") or "N/A",
            "flagged_codes_json": json.dumps(flagged, indent=2),
        }

        try:
            filled = _substitute(eval_prompt.prompt_template, ctx)
            llm_resp = await _call_llm(filled, eval_prompt.model, eval_prompt.temperature)
        except Exception as exc:
            logger.error("[DET-09] LLM evaluation failed (claim %s): %s", claim.claim_id, exc)
            return _deterministic()

        dispositions = llm_resp.get("code_dispositions", [])
        actionable = [d for d in dispositions if d.get("disposition") != "RETAIN"]
        if not actionable:
            # All codes verified correct — no finding needed.
            return DetectorResult(
                detector_code=self.code,
                finding_type="CPT_ON_INPATIENT_UB04",
                description=llm_resp.get("summary", f"CPT codes {codes_str} reviewed — no billing errors found."),
                overpayment_amount=0.0,
                confidence_score=0.0,
                evidence={
                    "cpt_codes": sorted({l.cpt_code for l in cpt_lines}),
                    "affected_line_ids": affected_ids,
                    "llm_dispositions": dispositions,
                    "all_retained": True,
                },
            )

        actionable_codes = {d["code"] for d in actionable}
        actionable_lines = [l for l in cpt_lines if l.cpt_code in actionable_codes]
        adjusted_overpayment = round(sum(l.paid_amount or 0.0 for l in actionable_lines), 2)

        return DetectorResult(
            detector_code=self.code,
            finding_type="CPT_ON_INPATIENT_UB04",
            description=llm_resp.get(
                "corrective_action_summary",
                f"CPT/HCPCS code(s) {', '.join(sorted(actionable_codes))} require correction on this UB-04 inpatient claim.",
            ),
            overpayment_amount=adjusted_overpayment,
            confidence_score=min(float(llm_resp.get("confidence", 0.85)), 0.97),
            evidence={
                "cpt_codes": sorted({l.cpt_code for l in cpt_lines}),
                "affected_line_ids": affected_ids,
                "llm_summary": llm_resp.get("summary"),
                "policy_basis": llm_resp.get("policy_basis"),
                "llm_dispositions": dispositions,
                "llm_confidence": llm_resp.get("confidence"),
            },
        )

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        results = []
        lines = claim.lines or []
        if not lines:
            return results

        # UB-04 inpatient: LLM-evaluated per code; skip DX-CPT / unbundling path.
        if (getattr(claim, "claim_form_type", None) == "UB-04"
                and getattr(claim, "care_setting", None) == "Inpatient"):
            cpt_lines = [l for l in lines if l.cpt_code]
            if cpt_lines:
                results.append(await self._evaluate_ub04_cpts(claim, cpt_lines))
            return results

        claim_cpts: Set[str] = {line.cpt_code for line in lines}

        # ── DX-CPT mismatch: query cpt_dx_coverage ────────────────────────
        # An 'excluded' pair means this ICD code indicates the CPT is not
        # medically necessary. Judged at the LINE level: a procedure is flagged
        # only when the contradicting diagnosis sits on the SAME service line, not
        # merely somewhere on the claim — so an unrelated dx pointed at a different
        # line (e.g. hypertension on an E/M line) can't taint a surgical line.
        # A line carrying no per-line dx falls back to the claim's primary_icd
        # (legacy/single-dx claims), preserving the original behaviour there.
        def _line_icds(line) -> list[str]:
            codes = line_diag_codes(line)
            if codes:
                return codes
            primary = (claim.primary_icd or "").strip()
            return [primary] if primary else []

        # (cpt, icd) pairs that actually co-occur on one line.
        line_pairs: Set[tuple] = set()
        for line in lines:
            for icd in _line_icds(line):
                line_pairs.add((line.cpt_code, icd))

        if line_pairs:
            res = await db_session.execute(
                select(CptDxCoverage).where(
                    CptDxCoverage.cpt_code.in_({c for c, _ in line_pairs}),
                    CptDxCoverage.icd_code.in_({i for _, i in line_pairs}),
                    CptDxCoverage.coverage_type == "excluded",
                )
            )
            # Keep only excluded rows whose (cpt, icd) is an actual same-line pair.
            excluded_pairs = [
                p for p in res.scalars().all()
                if (p.cpt_code, p.icd_code) in line_pairs
            ]

            for pair in excluded_pairs:
                _CERTAINTY_SCORE = {"mandatory": 0.90, "guideline": 0.70, "heuristic": 0.55}
                base_confidence = _CERTAINTY_SCORE.get(pair.rule_certainty, 0.70)
                confidence = round(base_confidence * pair.data_confidence, 3)

                # Only the lines where this CPT actually carries the excluded dx.
                affected_lines = [
                    l for l in lines
                    if l.cpt_code == pair.cpt_code and pair.icd_code in _line_icds(l)
                ]
                overpayment = sum(
                    (l.paid_amount or 0.0) for l in affected_lines
                )

                source = f"{pair.source_document} ({pair.source_authority})" if pair.source_document else "Clinical guidelines"
                results.append(DetectorResult(
                    detector_code=self.code,
                    finding_type="DX_CPT_MISMATCH",
                    description=(
                        f"Diagnosis {pair.icd_code} does not support procedure {pair.cpt_code}. "
                        f"{pair.rationale or ''} Source: {source}."
                    ),
                    overpayment_amount=round(overpayment, 2),
                    confidence_score=confidence,
                    evidence={
                        "cpt_code": pair.cpt_code,
                        "icd_code": pair.icd_code,
                        "coverage_type": pair.coverage_type,
                        "rule_certainty": pair.rule_certainty,
                        "data_confidence": pair.data_confidence,
                        "source_document": pair.source_document,
                        "source_authority": pair.source_authority,
                        "last_reviewed_at": pair.last_reviewed_at,
                        "affected_line_ids": [l.claim_line_id for l in affected_lines],
                        "overpayment": round(overpayment, 2),
                    },
                ))

        # ── Unbundling: component codes billed alongside comprehensive ────
        for global_code, component_codes in BUNDLED_CODES.items():
            if global_code in claim_cpts:
                unbundled = [c for c in component_codes if c in claim_cpts]
                if unbundled:
                    affected_lines = [l for l in lines if l.cpt_code in unbundled]
                    overpayment = sum((l.paid_amount or 0.0) for l in affected_lines)
                    # E/M-on-E/M (all codes 99xxx) is not surgical unbundling — it's
                    # multiple E/M visit levels for one same-day encounter, only one
                    # of which is payable. Report it as its own finding type so the
                    # wording matches the actual overpayment rationale.
                    is_em = global_code.startswith("99") and all(c.startswith("99") for c in unbundled)
                    if is_em:
                        finding_type = "MULTIPLE_EM_SAME_DAY"
                        description = (
                            f"Multiple E/M visit levels billed for the same encounter: {global_code} "
                            f"billed alongside {unbundled}. Only one E/M level is payable per provider "
                            f"per patient per day; the additional level(s) are not separately payable."
                        )
                    else:
                        finding_type = "UNBUNDLING"
                        description = (
                            f"Unbundling detected: {global_code} billed alongside component "
                            f"code(s) {unbundled} that are included in the comprehensive code."
                        )
                    results.append(DetectorResult(
                        detector_code=self.code,
                        finding_type=finding_type,
                        description=description,
                        overpayment_amount=round(overpayment, 2),
                        confidence_score=0.80,
                        evidence={
                            "global_code": global_code,
                            "unbundled_codes": unbundled,
                            "affected_line_ids": [l.claim_line_id for l in affected_lines],
                            "overpayment": round(overpayment, 2),
                        },
                    ))

        return results
