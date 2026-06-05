import json
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim
from ..models.reference import ModifierCode

_EM_PREFIXES = {"992", "993", "994", "995", "996", "997", "998", "999"}


def _is_em(cpt: str) -> bool:
    return any(cpt.startswith(p) for p in _EM_PREFIXES)


class ModifierIntegrityDetector(BaseDetector):
    code = "DET-16"
    name = "Modifier Integrity Detector"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        results = []
        lines = claim.lines or []
        if not lines:
            return results

        # Collect every modifier used across all lines.
        all_modifiers: set[str] = set()
        for line in lines:
            if (line.modifier_1 or "").strip():
                all_modifiers.add(line.modifier_1.strip())
            if (line.modifier_2 or "").strip():
                all_modifiers.add(line.modifier_2.strip())
        if not all_modifiers:
            return results

        # Single batch query — load reference data for all modifiers on this claim.
        res = await db_session.execute(
            select(ModifierCode).where(ModifierCode.code.in_(all_modifiers))
        )
        modifier_map: dict[str, ModifierCode] = {m.code: m for m in res.scalars().all()}

        # ── Check 1: unknown modifier ─────────────────────────────────────────
        for mod in sorted(all_modifiers):
            if mod not in modifier_map:
                affected = [
                    {"line_number": l.line_number, "cpt_code": l.cpt_code}
                    for l in lines
                    if (l.modifier_1 or "").strip() == mod or (l.modifier_2 or "").strip() == mod
                ]
                results.append(DetectorResult(
                    detector_code=self.code,
                    finding_type="UNKNOWN_MODIFIER",
                    description=(
                        f"Modifier '{mod}' is not a recognized CPT/HCPCS modifier. "
                        "Unrecognized modifiers will cause adjudication rejection or bypass "
                        "edits unintentionally."
                    ),
                    overpayment_amount=0.0,
                    confidence_score=0.93,
                    evidence={
                        "modifier": mod,
                        "affected_lines": affected,
                    },
                ))

        # ── Check 2 & 3: per-line checks ──────────────────────────────────────
        for line in lines:
            m1 = (line.modifier_1 or "").strip() or None
            m2 = (line.modifier_2 or "").strip() or None
            line_mods = [m for m in (m1, m2) if m and m in modifier_map]

            # Check 2: mutually exclusive pair on the same line.
            if m1 and m2 and m1 in modifier_map and m2 in modifier_map:
                ref1 = modifier_map[m1]
                exclusions = set(json.loads(ref1.mutually_exclusive_with or "[]"))
                if m2 in exclusions:
                    results.append(DetectorResult(
                        detector_code=self.code,
                        finding_type="MUTUALLY_EXCLUSIVE_MODIFIERS",
                        description=(
                            f"Modifiers {m1} and {m2} are mutually exclusive but both appear "
                            f"on line {line.line_number} (CPT {line.cpt_code}). "
                            "Only one may be used for a given service."
                        ),
                        overpayment_amount=round(line.paid_amount or 0.0, 2),
                        confidence_score=0.90,
                        evidence={
                            "line_number": line.line_number,
                            "cpt_code": line.cpt_code,
                            "modifier_1": m1,
                            "modifier_2": m2,
                            "line_id": line.claim_line_id,
                        },
                    ))

            # Check 3: modifier applied to wrong CPT type (prefix mismatch).
            for mod in line_mods:
                ref = modifier_map[mod]
                valid_prefixes = json.loads(ref.valid_cpt_prefixes or "[]")
                if not valid_prefixes:
                    continue  # no restriction defined — skip
                if not any(line.cpt_code.startswith(p) for p in valid_prefixes):
                    results.append(DetectorResult(
                        detector_code=self.code,
                        finding_type="MODIFIER_CPT_TYPE_MISMATCH",
                        description=(
                            f"Modifier {mod} is not applicable to CPT {line.cpt_code}. "
                            f"Valid CPT families for this modifier: "
                            f"{', '.join(valid_prefixes[:8])}{'…' if len(valid_prefixes) > 8 else ''}. "
                            f"Modifier {mod} applied to an incompatible procedure type."
                        ),
                        overpayment_amount=round(line.paid_amount or 0.0, 2),
                        confidence_score=round(0.85 * ref.data_confidence, 3),
                        evidence={
                            "line_number": line.line_number,
                            "cpt_code": line.cpt_code,
                            "modifier": mod,
                            "valid_cpt_prefixes": valid_prefixes,
                            "rule_certainty": ref.rule_certainty,
                            "line_id": line.claim_line_id,
                        },
                    ))

        # ── Check 4: modifier 25 without a same-day procedure ─────────────────
        # Modifier 25 means "significant, separately identifiable E/M on the same
        # day as a procedure." If there is no procedure line (non-E/M), there is
        # nothing for the E/M to be separate *from* — the modifier is unsupported.
        mod25_lines = [
            l for l in lines
            if (l.modifier_1 or "").strip() == "25" or (l.modifier_2 or "").strip() == "25"
        ]
        if mod25_lines:
            has_procedure = any(not _is_em(l.cpt_code) for l in lines)
            if not has_procedure:
                results.append(DetectorResult(
                    detector_code=self.code,
                    finding_type="MOD_25_WITHOUT_PROCEDURE",
                    description=(
                        "Modifier 25 present on E/M code(s) but no same-day procedure code "
                        "is billed on this claim. Modifier 25 is only valid when a significant, "
                        "separately identifiable E/M is performed on the same day as a procedure. "
                        "Without a procedure, modifier 25 has no basis."
                    ),
                    overpayment_amount=round(
                        sum(l.paid_amount or 0.0 for l in mod25_lines), 2
                    ),
                    confidence_score=0.82,
                    evidence={
                        "mod25_lines": [
                            {"line_number": l.line_number, "cpt_code": l.cpt_code,
                             "paid_amount": l.paid_amount}
                            for l in mod25_lines
                        ],
                        "claim_cpt_codes": sorted({l.cpt_code for l in lines}),
                    },
                ))

        return results
