"""seed_stage2_training_data.py — synthetic labeled claims for the Stage 2 model.

Real ground truth (confirmed_op = analyst RECOVERED decision) doesn't exist at
scale in the demo, so — exactly like the provider model's seed_training_data —
we synthesize claim-level feature rows [P_risk, F4, F5, F7, F8] and a latent
`confirmed_op` label the features drive. The label deliberately includes P_risk×
claim interaction terms: the spec's key point is that Modifier-59 revenue (F5)
from a high-P_risk provider is a categorically stronger signal than the same F5
from a clean provider. Overpayments are the rare class (~6%), matching the spec.

Not real claims — a training surface. Inference extracts the same five features
from real claims via stage2_features.compute_features.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .stage2_features import STAGE2_FEATURE_COLS, TARGET_COL


def generate_training_data(n: int = 6000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.RandomState(seed)

    # Feature marginals chosen to resemble adjudicated professional claims.
    p_risk = np.clip(rng.beta(1.6, 4.0, n), 0.0, 1.0)          # provider reputation, skewed low
    f4 = np.clip(rng.beta(1.5, 5.0, n), 0.0, 1.0)             # high-value CPT ratio
    f5 = np.clip(rng.beta(1.2, 9.0, n), 0.0, 1.0)             # modifier value-add, mostly ~0
    f7 = np.clip(np.abs(rng.normal(1.0, 0.45, n))             # units vs specialty norm ~1
                 + rng.exponential(0.15, n), 0.0, 10.0)
    f8 = rng.binomial(1, 0.6, n).astype(float)               # multi-line flag

    # Latent overpayment propensity. Base tuned for ~6% positives; P_risk both
    # a main effect and an amplifier of the claim-level signals.
    logit = (
        -6.2
        + 4.2 * p_risk
        + 3.0 * f4
        + 4.0 * f5
        + 1.1 * np.clip(f7 - 1.0, 0.0, None)
        + 0.5 * f8
        + 3.2 * p_risk * f5          # risky provider + modifier revenue
        + 1.8 * p_risk * f4          # risky provider + high-value coding
        + rng.normal(0.0, 0.28, n)   # irreducible noise
    )
    prob = 1.0 / (1.0 + np.exp(-logit))
    y = rng.binomial(1, prob)

    df = pd.DataFrame({
        "P_risk": p_risk, "F4": f4, "F5": f5, "F7": f7, "F8": f8,
        TARGET_COL: y,
    })
    return df[STAGE2_FEATURE_COLS + [TARGET_COL]]


if __name__ == "__main__":
    d = generate_training_data()
    print(f"rows={len(d)}  positive_rate={d[TARGET_COL].mean():.3f}")
    print(d.describe().round(3).to_string())
