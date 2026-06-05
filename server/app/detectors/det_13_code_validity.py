from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim, line_diag_codes
from ..models.reference import CptCode, IcdCode, DrgCode, ModifierCode, CptModifierMap


class CodeValidityDetector(BaseDetector):
    code = "DET-13"
    name = "Code Validity"

    async def run(self, claim: Claim, db_session: AsyncSession) -> List[DetectorResult]:
        lines = claim.lines or []
        results = []

        # ── Collect codes from claim ───────────────────────────────────────
        cpt_billed: set[str] = {
            line.cpt_code.strip()
            for line in lines
            if line.cpt_code and line.cpt_code.strip()
        }
        icd_billed: set[str] = set()
        if claim.primary_icd and claim.primary_icd.strip():
            icd_billed.add(claim.primary_icd.strip())
        for line in lines:
            icd_billed |= set(line_diag_codes(line))

        # modifier tuples: (cpt_code, modifier_code)
        modifier_pairs: set[tuple[str, str]] = set()
        for line in lines:
            cpt = line.cpt_code.strip() if line.cpt_code else None
            if not cpt:
                continue
            for mod_field in (line.modifier_1, line.modifier_2):
                if mod_field and mod_field.strip():
                    modifier_pairs.add((cpt, mod_field.strip()))

        modifier_codes_billed = {m for _, m in modifier_pairs}

        dos = (claim.service_from_date or "").strip()  # "YYYY-MM-DD" or ""

        # ── CPT validity + effective-date check ───────────────────────────
        invalid_cpt: list[str] = []
        inactive_cpt: list[tuple[str, str]] = []   # (code, reason)
        known_cpt: set[str] = set()
        if cpt_billed:
            res = await db_session.execute(
                select(CptCode.code, CptCode.effective_date, CptCode.termination_date)
                .where(CptCode.code.in_(cpt_billed))
            )
            rows = res.all()
            known_cpt = {r[0] for r in rows}
            invalid_cpt = sorted(cpt_billed - known_cpt)
            if dos:
                for code, eff, term in rows:
                    if eff and dos < eff:
                        inactive_cpt.append((code, f"not effective until {eff}"))
                    elif term and dos > term:
                        inactive_cpt.append((code, f"terminated {term}"))

        # ── ICD-10 validity + effective-date check ────────────────────────
        invalid_icd: list[str] = []
        inactive_icd: list[tuple[str, str]] = []   # (code, reason)
        if icd_billed:
            res = await db_session.execute(
                select(IcdCode.code, IcdCode.effective_date, IcdCode.termination_date)
                .where(IcdCode.code.in_(icd_billed))
            )
            rows = res.all()
            known_icd = {r[0] for r in rows}
            invalid_icd = sorted(icd_billed - known_icd)
            if dos:
                for code, eff, term in rows:
                    if eff and dos < eff:
                        inactive_icd.append((code, f"not effective until {eff}"))
                    elif term and dos > term:
                        inactive_icd.append((code, f"terminated {term}"))

        # ── Modifier existence check ───────────────────────────────────────
        invalid_modifiers: list[str] = []
        known_modifiers: set[str] = set()
        if modifier_codes_billed:
            res = await db_session.execute(
                select(ModifierCode.code).where(ModifierCode.code.in_(modifier_codes_billed))
            )
            known_modifiers = {row[0] for row in res.all()}
            invalid_modifiers = sorted(modifier_codes_billed - known_modifiers)

        # ── CPT + modifier pair validity ──────────────────────────────────
        invalid_cpt_mod_pairs: list[tuple[str, str]] = []
        if modifier_pairs:
            # Only check pairs where both CPT and modifier are individually known
            checkable = {(c, m) for c, m in modifier_pairs
                         if c in known_cpt and m in known_modifiers}
            if checkable:
                cpts_to_check = {c for c, _ in checkable}
                mods_to_check = {m for _, m in checkable}
                res = await db_session.execute(
                    select(CptModifierMap.cpt_code, CptModifierMap.modifier_code).where(
                        CptModifierMap.cpt_code.in_(cpts_to_check),
                        CptModifierMap.modifier_code.in_(mods_to_check),
                    )
                )
                valid_pairs = {(row[0], row[1]) for row in res.all()}
                invalid_cpt_mod_pairs = sorted(checkable - valid_pairs)

        # ── DRG validity (only when claim carries a DRG) ──────────────────
        invalid_drg: str | None = None
        if claim.drg and claim.drg.strip():
            res = await db_session.execute(
                select(DrgCode.code).where(DrgCode.code == claim.drg.strip())
            )
            if res.scalar_one_or_none() is None:
                invalid_drg = claim.drg.strip()

        if not any([invalid_cpt, invalid_icd, inactive_cpt, inactive_icd,
                    invalid_modifiers, invalid_cpt_mod_pairs, invalid_drg]):
            return []

        # ── Build findings — one per category so each is independently actionable
        if invalid_cpt or invalid_icd:
            parts = []
            if invalid_cpt:
                parts.append(f"CPT: {', '.join(invalid_cpt)}")
            if invalid_icd:
                parts.append(f"ICD-10: {', '.join(invalid_icd)}")
            results.append(DetectorResult(
                detector_code=self.code,
                finding_type="INVALID_CODE",
                description=(
                    "Code(s) not found in loaded CMS reference tables — "
                    + "; ".join(parts)
                    + ". Verify codes are valid and effective for the date of service."
                ),
                overpayment_amount=0.0,
                confidence_score=0.75,
                evidence={
                    "invalid_cpt_codes": invalid_cpt,
                    "invalid_icd_codes": invalid_icd,
                    "cpt_codes_checked": sorted(cpt_billed),
                    "icd_codes_checked": sorted(icd_billed),
                },
            ))

        if inactive_cpt or inactive_icd:
            parts = []
            for code, reason in sorted(inactive_cpt):
                parts.append(f"CPT {code}: {reason}")
            for code, reason in sorted(inactive_icd):
                parts.append(f"ICD-10 {code}: {reason}")
            results.append(DetectorResult(
                detector_code=self.code,
                finding_type="INACTIVE_CODE",
                description=(
                    "Code(s) found in reference tables but inactive on the date of service "
                    f"({dos}): " + "; ".join(parts) + "."
                ),
                overpayment_amount=0.0,
                confidence_score=0.90,
                evidence={
                    "service_date": dos,
                    "inactive_cpt": [{"code": c, "reason": r} for c, r in sorted(inactive_cpt)],
                    "inactive_icd": [{"code": c, "reason": r} for c, r in sorted(inactive_icd)],
                },
            ))

        if invalid_modifiers:
            results.append(DetectorResult(
                detector_code=self.code,
                finding_type="INVALID_MODIFIER",
                description=(
                    f"Modifier(s) not found in reference table: {', '.join(invalid_modifiers)}. "
                    "Verify modifiers are valid CMS/AMA modifiers for the date of service."
                ),
                overpayment_amount=0.0,
                confidence_score=0.80,
                evidence={"invalid_modifiers": invalid_modifiers},
            ))

        if invalid_cpt_mod_pairs:
            pair_strs = [f"{c}+{m}" for c, m in invalid_cpt_mod_pairs]
            results.append(DetectorResult(
                detector_code=self.code,
                finding_type="INVALID_CPT_MODIFIER_PAIR",
                description=(
                    f"CPT-modifier combination(s) not recognized as valid: {', '.join(pair_strs)}. "
                    "Verify the modifier is applicable to the billed procedure per CMS/AMA rules."
                ),
                overpayment_amount=0.0,
                confidence_score=0.70,
                evidence={"invalid_pairs": [{"cpt": c, "modifier": m} for c, m in invalid_cpt_mod_pairs]},
            ))

        if invalid_drg:
            results.append(DetectorResult(
                detector_code=self.code,
                finding_type="INVALID_DRG",
                description=(
                    f"DRG '{invalid_drg}' not found in the MS-DRG reference table. "
                    "Verify the DRG code is valid for the applicable fiscal year."
                ),
                overpayment_amount=0.0,
                confidence_score=0.85,
                evidence={"invalid_drg": invalid_drg, "claim_drg": claim.drg},
            ))

        return results
