"""
seed_training_data.py

Generates 5,000 synthetic rows representing 12 months of provider
billing patterns for training billing_variance_classifier.

Each row represents one monthly provider snapshot with 7 features
plus the binary target had_confirmed_overpayment.

Output: seed/outputs/training_data.csv
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

FEATURE_COLS = [
    "avg_units_per_line",
    "high_value_cpt_ratio",
    "multi_line_claim_ratio",
    "modifier_usage_rate",
    "same_day_multi_cpt_rate",
    "prior_overpayment_rate",
    "specialty_peer_deviation",
]

TARGET_COL = "had_confirmed_overpayment"
ROWS_PER_PROVIDER = 500
NOISE_FRACTION = 0.15      # 15 % of rows are pure noise
RANDOM_SEED = 42

# ---------------------------------------------------------------------------
# Provider profiles
# Each entry: anomaly_rate + per-feature (mean, std)
# Column order matches FEATURE_COLS exactly.
# ---------------------------------------------------------------------------

PROVIDER_PROFILES: dict[str, dict[str, Any]] = {
    # ── High-anomaly profiles ──────────────────────────────────────────────
    "1111111111": {
        "profile": "cardiology_high",
        "anomaly_rate": 0.35,
        "features": {
            #                                          mean   std
            "avg_units_per_line":       (3.2,  0.8),
            "high_value_cpt_ratio":     (0.75, 0.12),
            "multi_line_claim_ratio":   (0.65, 0.10),
            "modifier_usage_rate":      (0.68, 0.15),
            "same_day_multi_cpt_rate":  (0.45, 0.12),
            "prior_overpayment_rate":   (0.32, 0.08),
            "specialty_peer_deviation": (2.1,  0.6),
        },
    },
    "1111111112": {
        "profile": "ortho_high",
        "anomaly_rate": 0.28,
        "features": {
            "avg_units_per_line":       (2.8,  0.7),
            "high_value_cpt_ratio":     (0.70, 0.11),
            "multi_line_claim_ratio":   (0.55, 0.09),
            "modifier_usage_rate":      (0.60, 0.13),
            "same_day_multi_cpt_rate":  (0.38, 0.10),
            "prior_overpayment_rate":   (0.26, 0.07),
            "specialty_peer_deviation": (1.8,  0.5),
        },
    },
    "1111111114": {
        "profile": "internal_high",
        "anomaly_rate": 0.42,
        "features": {
            "avg_units_per_line":       (2.5,  0.9),
            "high_value_cpt_ratio":     (0.55, 0.14),
            "multi_line_claim_ratio":   (0.70, 0.11),
            "modifier_usage_rate":      (0.72, 0.16),
            "same_day_multi_cpt_rate":  (0.50, 0.13),
            "prior_overpayment_rate":   (0.40, 0.09),
            "specialty_peer_deviation": (2.4,  0.7),
        },
    },
    # ── Standard-anomaly profiles ─────────────────────────────────────────
    "1111111113": {
        "profile": "neuro_standard",
        "anomaly_rate": 0.18,
        "features": {
            "avg_units_per_line":       (2.0,  0.6),
            "high_value_cpt_ratio":     (0.45, 0.11),
            "multi_line_claim_ratio":   (0.48, 0.09),
            "modifier_usage_rate":      (0.42, 0.12),
            "same_day_multi_cpt_rate":  (0.28, 0.09),
            "prior_overpayment_rate":   (0.16, 0.06),
            "specialty_peer_deviation": (0.8,  0.5),
        },
    },
    "2222222221": {
        "profile": "cardiology_std",
        "anomaly_rate": 0.15,
        "features": {
            "avg_units_per_line":       (1.9,  0.6),
            "high_value_cpt_ratio":     (0.42, 0.10),
            "multi_line_claim_ratio":   (0.45, 0.09),
            "modifier_usage_rate":      (0.38, 0.11),
            "same_day_multi_cpt_rate":  (0.25, 0.08),
            "prior_overpayment_rate":   (0.13, 0.05),
            "specialty_peer_deviation": (0.5,  0.4),
        },
    },
    "2222222222": {
        "profile": "emergency_std",
        "anomaly_rate": 0.22,
        "features": {
            "avg_units_per_line":       (2.2,  0.7),
            "high_value_cpt_ratio":     (0.50, 0.12),
            "multi_line_claim_ratio":   (0.52, 0.09),
            "modifier_usage_rate":      (0.48, 0.13),
            "same_day_multi_cpt_rate":  (0.32, 0.09),
            "prior_overpayment_rate":   (0.20, 0.06),
            "specialty_peer_deviation": (1.2,  0.5),
        },
    },
    "3333333331": {
        "profile": "ortho_std",
        "anomaly_rate": 0.18,
        "features": {
            "avg_units_per_line":       (2.0,  0.6),
            "high_value_cpt_ratio":     (0.44, 0.10),
            "multi_line_claim_ratio":   (0.47, 0.08),
            "modifier_usage_rate":      (0.42, 0.11),
            "same_day_multi_cpt_rate":  (0.28, 0.09),
            "prior_overpayment_rate":   (0.15, 0.05),
            "specialty_peer_deviation": (0.7,  0.4),
        },
    },
    "3333333333": {
        "profile": "pt_moderate",
        "anomaly_rate": 0.25,
        "features": {
            "avg_units_per_line":       (2.3,  0.7),
            "high_value_cpt_ratio":     (0.52, 0.11),
            "multi_line_claim_ratio":   (0.55, 0.09),
            "modifier_usage_rate":      (0.52, 0.12),
            "same_day_multi_cpt_rate":  (0.35, 0.10),
            "prior_overpayment_rate":   (0.22, 0.07),
            "specialty_peer_deviation": (1.4,  0.5),
        },
    },
    # ── Low-anomaly profiles ──────────────────────────────────────────────
    "2222222223": {
        "profile": "internal_low",
        "anomaly_rate": 0.10,
        "features": {
            "avg_units_per_line":       (1.6,  0.5),
            "high_value_cpt_ratio":     (0.25, 0.09),
            "multi_line_claim_ratio":   (0.38, 0.08),
            "modifier_usage_rate":      (0.28, 0.10),
            "same_day_multi_cpt_rate":  (0.18, 0.07),
            "prior_overpayment_rate":   (0.08, 0.04),
            "specialty_peer_deviation": (-0.2, 0.4),
        },
    },
    "3333333332": {
        "profile": "radiology_low",
        "anomaly_rate": 0.08,
        "features": {
            "avg_units_per_line":       (1.4,  0.4),
            "high_value_cpt_ratio":     (0.18, 0.07),
            "multi_line_claim_ratio":   (0.30, 0.07),
            "modifier_usage_rate":      (0.22, 0.09),
            "same_day_multi_cpt_rate":  (0.12, 0.06),
            "prior_overpayment_rate":   (0.06, 0.03),
            "specialty_peer_deviation": (-0.5, 0.3),
        },
    },
}

# Clipping bounds per feature
_CLIP = {
    "avg_units_per_line":       (1.0, 6.0),
    "high_value_cpt_ratio":     (0.0, 1.0),
    "multi_line_claim_ratio":   (0.0, 1.0),
    "modifier_usage_rate":      (0.0, 1.0),
    "same_day_multi_cpt_rate":  (0.0, 1.0),
    "prior_overpayment_rate":   (0.0, 1.0),
    "specialty_peer_deviation": (-3.0, 3.0),
}

# Class-conditional shifts: when a row's label is positive (overpayment), the
# feature mean is shifted by `mean_shift` (additive) before sampling.
# Calibrated to produce realistic class separation — confirmed-overpayment
# providers DO have measurably higher values on these signals in real audits.
_POSITIVE_SHIFT: dict[str, float] = {
    "avg_units_per_line":       1.2,
    "high_value_cpt_ratio":     0.20,
    "multi_line_claim_ratio":   0.15,
    "modifier_usage_rate":      0.20,
    "same_day_multi_cpt_rate":  0.15,
    "prior_overpayment_rate":   0.25,
    "specialty_peer_deviation": 1.5,
}

# Reduce noise so the signal isn't drowned out.
NOISE_FRACTION = 0.08    # was 0.15; tighter now that signal is real


def _generate_provider_rows(
    npi: str,
    profile: dict[str, Any],
    n_rows: int,
    rng: np.random.Generator,
) -> list[dict]:
    rows = []
    n_noise = int(n_rows * NOISE_FRACTION)
    n_normal = n_rows - n_noise

    feature_dists = profile["features"]
    anomaly_rate = profile["anomaly_rate"]

    # Class-conditional rows. Decide label FIRST, then sample features from
    # the appropriate class distribution (positives get shifted means).
    for _ in range(n_normal):
        label = int(rng.random() < anomaly_rate)
        row: dict[str, Any] = {"provider_npi": npi}
        for feat in FEATURE_COLS:
            base_mean, std = feature_dists[feat]
            mean = base_mean + (_POSITIVE_SHIFT[feat] if label == 1 else 0.0)
            val = float(rng.normal(mean, std))
            lo, hi = _CLIP[feat]
            row[feat] = max(lo, min(hi, val))
        row[TARGET_COL] = label
        rows.append(row)

    # Noise rows: completely random features with random label (acts as a
    # regularizer — model can't perfectly memorize without overfitting).
    for _ in range(n_noise):
        row = {"provider_npi": npi}
        for feat in FEATURE_COLS:
            lo, hi = _CLIP[feat]
            row[feat] = float(rng.uniform(lo, hi))
        row[TARGET_COL] = int(rng.random() < 0.25)
        rows.append(row)

    return rows


def generate_training_data(
    n_rows: int = 5_000,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """
    Generate synthetic training data for billing_variance_classifier.

    Returns a DataFrame with FEATURE_COLS + TARGET_COL + provider_npi.
    Total rows ≈ n_rows (may differ slightly due to rounding per provider).
    """
    rng = np.random.default_rng(seed)
    random.seed(seed)

    npis = list(PROVIDER_PROFILES.keys())
    rows_per = n_rows // len(npis)         # ~500 per provider for 10 providers

    all_rows: list[dict] = []
    for npi in npis:
        profile = PROVIDER_PROFILES[npi]
        rows = _generate_provider_rows(npi, profile, rows_per, rng)
        all_rows.extend(rows)

    # If rounding left us short, pad with rows from the first provider
    while len(all_rows) < n_rows:
        extra = _generate_provider_rows(npis[0], PROVIDER_PROFILES[npis[0]], 1, rng)
        all_rows.extend(extra)

    rng.shuffle(all_rows)                  # shuffle so providers are interleaved

    df = pd.DataFrame(all_rows)
    df = df[["provider_npi"] + FEATURE_COLS + [TARGET_COL]].copy()
    df[TARGET_COL] = df[TARGET_COL].astype(int)

    return df


def save_training_data(df: pd.DataFrame, path: str | Path | None = None) -> Path:
    """Save training data CSV and return the path."""
    if path is None:
        here = Path(__file__).resolve().parent.parent.parent   # server/
        path = here / "seed" / "outputs" / "training_data.csv"

    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    return out_path


if __name__ == "__main__":
    df = generate_training_data()
    print(f"Generated {len(df)} rows")
    print(f"Positive rate: {df[TARGET_COL].mean():.3f}")
    print(f"Rows per provider:\n{df.groupby('provider_npi').size().to_string()}")
    p = save_training_data(df)
    print(f"Saved → {p}")
