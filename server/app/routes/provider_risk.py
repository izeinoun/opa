"""Provider risk explainability — per-provider SHAP attribution + plain English.

Surfaces *why* the model assigned each provider their billing_variance_score.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from ..middleware.auth import require_app
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware.auth import get_current_user
from ..models.workflow import OpaUser
from ..models.reference import Provider
from ..ml.train_billing_variance import FEATURE_COLS, TARGET_COL, load_model


router = APIRouter(prefix="/api/provider-risk", tags=["provider-risk"], dependencies=[Depends(require_app("payguard"))])

_TRAINING_CSV = Path(__file__).resolve().parent.parent.parent / "seed" / "outputs" / "training_data.csv"


# ── Plain-English templating ──────────────────────────────────────────────

_FEATURE_LABEL = {
    "avg_units_per_line":       "average units per claim line",
    "high_value_cpt_ratio":     "high-risk CPT ratio",
    "multi_line_claim_ratio":   "share of multi-line claims",
    "modifier_usage_rate":      "modifier usage rate",
    "same_day_multi_cpt_rate":  "same-day multiple-CPT rate",
    "prior_overpayment_rate":   "prior overpayment rate",
    "specialty_peer_deviation": "specialty peer deviation (z-score)",
}

_FORMAT = {
    "avg_units_per_line":       lambda v: f"{v:.2f}",
    "high_value_cpt_ratio":     lambda v: f"{v*100:.0f}%",
    "multi_line_claim_ratio":   lambda v: f"{v*100:.0f}%",
    "modifier_usage_rate":      lambda v: f"{v*100:.0f}%",
    "same_day_multi_cpt_rate":  lambda v: f"{v*100:.0f}%",
    "prior_overpayment_rate":   lambda v: f"{v*100:.0f}%",
    "specialty_peer_deviation": lambda v: f"{v:+.2f}",
}


def _adjective(provider_val: float, pop_mean: float, pop_std: float) -> str:
    """Tier the deviation magnitude into a readable adjective."""
    if pop_std == 0:
        return "above average" if provider_val > pop_mean else "below average"
    z = (provider_val - pop_mean) / pop_std
    if z >= 2.0:   return "significantly elevated"
    if z >= 1.0:   return "elevated"
    if z >= 0.3:   return "above average"
    if z <= -2.0:  return "significantly below average"
    if z <= -1.0:  return "below average"
    if z <= -0.3:  return "slightly below average"
    return "near the population average"


def _band(score: float) -> str:
    if score >= 0.65: return "HIGH"
    if score >= 0.35: return "MEDIUM"
    return "LOW"


# ── API shapes ────────────────────────────────────────────────────────────

class DriverFactor(BaseModel):
    feature: str               # raw feature name (e.g. prior_overpayment_rate)
    label: str                 # human label
    provider_value: float
    provider_value_fmt: str    # formatted ("45%" or "+2.34")
    population_mean: float
    population_mean_fmt: str
    shap_contribution: float   # positive = pushes score up, negative = pushes down
    direction: str             # "raises" | "lowers" | "neutral"


class ProviderRiskExplanation(BaseModel):
    npi: str
    name: str
    specialty: str
    score: float
    band: str
    top_drivers: List[DriverFactor]
    plain_english: str
    n_claims_in_system: int    # how many claims this provider has in the live DB


# ── Compute path ──────────────────────────────────────────────────────────

def _provider_feature_vector(df_train: pd.DataFrame, npi: str) -> Optional[np.ndarray]:
    sub = df_train[df_train["provider_npi"].astype(str) == str(npi)]
    if sub.empty:
        return None
    return sub[FEATURE_COLS].mean().values.astype(float).reshape(1, -1)


def _build_explanation(
    npi: str, name: str, specialty: str,
    provider_vec: np.ndarray,           # shape (1, n_features), un-scaled
    score: float,
    shap_row: np.ndarray,               # shape (n_features,)
    pop_stats: dict,                    # {feat: (mean, std)} on raw (un-scaled) features
    n_claims_in_system: int,
) -> ProviderRiskExplanation:
    provider_vec_flat = provider_vec.flatten()
    pairs = list(zip(FEATURE_COLS, provider_vec_flat, shap_row))
    # Top 3 by absolute SHAP contribution
    pairs.sort(key=lambda p: -abs(p[2]))
    top = pairs[:3]

    drivers: List[DriverFactor] = []
    for feat, val, contrib in top:
        mean, _std = pop_stats[feat]
        direction = "raises" if contrib > 1e-4 else ("lowers" if contrib < -1e-4 else "neutral")
        drivers.append(DriverFactor(
            feature=feat,
            label=_FEATURE_LABEL[feat],
            provider_value=float(val),
            provider_value_fmt=_FORMAT[feat](val),
            population_mean=float(mean),
            population_mean_fmt=_FORMAT[feat](mean),
            shap_contribution=float(contrib),
            direction=direction,
        ))

    # Plain English
    band = _band(score)
    lead = f"{name} has a billing variance score of {score:.2f} ({band})."
    if not drivers:
        plain = lead
    else:
        sentences = [lead]
        top_pos = [d for d in drivers if d.direction == "raises"]
        top_neg = [d for d in drivers if d.direction == "lowers"]

        if top_pos:
            d = top_pos[0]
            mean, std = pop_stats[d.feature]
            adj = _adjective(d.provider_value, mean, std)
            sentences.append(
                f"The biggest upward driver is {d.label} at {d.provider_value_fmt}, "
                f"compared to the typical provider at {d.population_mean_fmt} — {adj}."
            )
            if len(top_pos) >= 2:
                d2 = top_pos[1]
                m2, s2 = pop_stats[d2.feature]
                sentences.append(
                    f"Also contributing: {d2.label} at {d2.provider_value_fmt} "
                    f"(typical {d2.population_mean_fmt}, {_adjective(d2.provider_value, m2, s2)})."
                )
        if top_neg:
            d = top_neg[0]
            mean, std = pop_stats[d.feature]
            sentences.append(
                f"Working in their favor: {d.label} at {d.provider_value_fmt} "
                f"({_adjective(d.provider_value, mean, std)} — below typical {d.population_mean_fmt})."
            )
        plain = " ".join(sentences)

    return ProviderRiskExplanation(
        npi=npi, name=name, specialty=specialty,
        score=score, band=band,
        top_drivers=drivers,
        plain_english=plain,
        n_claims_in_system=n_claims_in_system,
    )


@router.get("", response_model=List[ProviderRiskExplanation])
async def list_provider_risk(
    db: AsyncSession = Depends(get_db),
    current_user: OpaUser = Depends(get_current_user),
) -> List[ProviderRiskExplanation]:
    if current_user.role not in ("supervisor", "admin"):
        raise HTTPException(status_code=403, detail="Supervisor or admin role required")

    try:
        clf, scaler = load_model()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Model artifact not found — retrain first")

    if not _TRAINING_CSV.exists():
        raise HTTPException(status_code=503, detail="Training data not found")

    df_train = pd.read_csv(_TRAINING_CSV)

    # Population stats on un-scaled features (for plain-English comparisons)
    pop_stats: dict = {
        feat: (float(df_train[feat].mean()), float(df_train[feat].std()))
        for feat in FEATURE_COLS
    }

    # All providers from the live DB
    res = await db.execute(select(Provider))
    providers = list(res.scalars().all())

    # Claim counts per NPI (for "n_claims_in_system")
    import sqlite3
    db_path = "./opa.db"
    counts: dict = {}
    try:
        sconn = sqlite3.connect(db_path)
        for npi, n in sconn.execute(
            "SELECT rendering_provider_npi, COUNT(*) FROM claims GROUP BY rendering_provider_npi"
        ):
            counts[str(npi)] = int(n)
        sconn.close()
    except Exception:
        pass

    # SHAP explainer (TreeExplainer is fast for RandomForest)
    import shap
    explainer = shap.TreeExplainer(clf)

    out: List[ProviderRiskExplanation] = []
    for p in providers:
        vec = _provider_feature_vector(df_train, p.npi)
        if vec is None:
            # Provider in DB but not in training data — skip
            continue
        scaled = scaler.transform(vec)
        # SHAP for the positive class
        sv = explainer.shap_values(scaled)
        # shap returns either (n_samples, n_features) or (n_samples, n_features, n_classes)
        sv = np.array(sv)
        if sv.ndim == 3:
            # (samples, features, classes) — pick positive class
            shap_row = sv[0, :, 1]
        elif sv.ndim == 2:
            shap_row = sv[0, :]
        else:
            shap_row = sv
        out.append(_build_explanation(
            npi=p.npi,
            name=p.name,
            specialty=p.specialty,
            provider_vec=vec,
            score=float(p.billing_variance_score or 0.0),
            shap_row=np.asarray(shap_row, dtype=float),
            pop_stats=pop_stats,
            n_claims_in_system=counts.get(str(p.npi), 0),
        ))

    out.sort(key=lambda e: -e.score)
    return out
