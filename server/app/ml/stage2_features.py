"""stage2_features.py — Stage 2 Claim Predictor feature definitions.

Implements the five inputs from the Stage 2 Feature Specification v1.3:

    P_risk  Provider Reputation Score — the calibrated Stage 1 output, injected
            as a feature (the cross-stage hand-off). NOT scaled.
    F4      High-Value CPT Ratio      — high-risk CPT lines / total lines.
    F5      Modifier Value-Add Ratio  — $ from payment-driving modifiers above the
            fee schedule / total allowed, clipped [0,1].
    F7      Avg Units per Line        — mean(units) / specialty-norm units, clipped [0,10].
    F8      Multi-Line Flag           — 1 if >1 service line else 0. NOT scaled.

The same `compute_features` is used at training-data assembly and at inference
(scoring a real claim). Reference constants are versioned here; the spec calls
for loading them from versioned files at startup — for the demo they live in
code with an explicit version string.

Fields consumed per line: cpt_code, modifier_1, modifier_2, units, allowed_amount,
fee_schedule_amount. Missing fee_schedule_amount → that line contributes 0 to F5.
"""
from __future__ import annotations

from typing import Any, Optional

# Feature order is a hard contract (scaler + model expect this order).
STAGE2_FEATURE_COLS = ["P_risk", "F4", "F5", "F7", "F8"]
# Only these are StandardScaler'd; P_risk (already 0-1) and F8 (binary) pass through.
STAGE2_SCALED_COLS = ["F4", "F5", "F7"]
TARGET_COL = "confirmed_op"

REFERENCE_VERSION = "v1.0-illustrative"

# HIGH_RISK_CPTS — illustrative Phase 1 list (spec §6, F4). Replace pre-production
# with a payer-specific list mined from confirmed RECOVERED cases.
HIGH_RISK_CPTS = {
    "99215", "99214", "93000", "70553", "27447",
    "43239", "64483", "62323", "G0439", "90837",
}

# HIGH_RISK_MODIFIERS — payment-driving modifiers (spec §6, F5). LT/RT excluded
# (clinically necessary bilateral markers, low fraud signal).
HIGH_RISK_MODIFIERS = {"25", "59", "76", "77", "GT", "95"}

# SPECIALTY_NORM_UNITS — expected units/line per specialty (spec §6, F7). The spec
# keys these by CMS numeric code; our providers carry specialty NAMES, so the
# table is keyed by name with the same norms. DEFAULT for anything unlisted.
_SPECIALTY_DEFAULT = 1.3
SPECIALTY_NORM_UNITS = {
    "General Practice": 1.2, "Family Medicine": 1.2, "Internal Medicine": 1.2,
    "Cardiology": 1.5,
    "Orthopedic Surgery": 1.8, "Orthopedics": 1.8,
    "Psychiatry": 1.4, "Mental Health": 1.4, "Behavioral Health": 1.4,
    "Neurology": 1.6,
    "Ophthalmology": 2.1,
    "Dermatology": 1.3,
    "Emergency Medicine": 1.4,
}


def specialty_norm(specialty: Optional[str]) -> float:
    """Look up the specialty units norm; DEFAULT (1.3) for unknown/None."""
    if not specialty:
        return _SPECIALTY_DEFAULT
    return SPECIALTY_NORM_UNITS.get(specialty.strip(), _SPECIALTY_DEFAULT)


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def compute_features(
    p_risk: float,
    lines: list[dict[str, Any]],
    specialty: Optional[str],
) -> dict[str, float]:
    """Compute [P_risk, F4, F5, F7, F8] from a single claim's service lines.

    `lines` items use keys: cpt_code, modifier_1, modifier_2, units,
    allowed_amount, fee_schedule_amount (fee_schedule_amount may be None → 0 F5).
    """
    n = len(lines)
    if n == 0:
        return {"P_risk": float(p_risk), "F4": 0.0, "F5": 0.0, "F7": 0.0, "F8": 0.0}

    # F4 — High-Value CPT Ratio
    hi = sum(1 for ln in lines if str(ln.get("cpt_code", "")).strip() in HIGH_RISK_CPTS)
    f4 = hi / n

    # F5 — Modifier Value-Add Ratio: $ from high-risk-modifier lines above fee
    # schedule, over total allowed. Clipped [0,1].
    total_allowed = sum(float(ln.get("allowed_amount") or 0.0) for ln in lines)
    mod_delta = 0.0
    for ln in lines:
        mods = {str(ln.get("modifier_1") or "").strip(), str(ln.get("modifier_2") or "").strip()}
        if mods & HIGH_RISK_MODIFIERS:
            allowed = float(ln.get("allowed_amount") or 0.0)
            fee = ln.get("fee_schedule_amount")
            if fee is not None:
                mod_delta += allowed - float(fee)
    f5 = _clip(mod_delta / total_allowed, 0.0, 1.0) if total_allowed > 0 else 0.0

    # F7 — Avg Units per Line, specialty-adjusted. Clipped [0,10].
    mean_units = sum(float(ln.get("units") or 0.0) for ln in lines) / n
    f7 = _clip(mean_units / specialty_norm(specialty), 0.0, 10.0)

    # F8 — Multi-Line Flag
    f8 = 1.0 if n > 1 else 0.0

    return {"P_risk": float(p_risk), "F4": float(f4), "F5": float(f5), "F7": float(f7), "F8": float(f8)}
