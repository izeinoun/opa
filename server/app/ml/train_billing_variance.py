"""
train_billing_variance.py

Trains the billing_variance_classifier model using sklearn RandomForestClassifier.

Public API
----------
    result = train_model(df)           # returns dict with scores + metrics
    write_scores_to_db(result["provider_scores"])
    score = score_provider(features)   # float 0-1

Result dict keys:
    success, method, model_artifact_id, accuracy, positive_rate,
    training_rows, feature_importance, provider_scores
"""

from __future__ import annotations

import os
import pickle
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler

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
MODEL_NAME = "billing_variance_classifier"

_ML_MODELS_DIR = Path(os.getenv("ML_MODELS_DIR", "./ml_models"))
_ARTIFACT_PATH = _ML_MODELS_DIR / f"{MODEL_NAME}.pkl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(val: float, min_val: float, max_val: float) -> float:
    return max(0.0, min(1.0, (val - min_val) / (max_val - min_val)))


def _formula_score(features: "pd.Series") -> float:
    """Weighted heuristic score used when the saved artifact is absent."""
    f = features
    return min(1.0, (
        f["prior_overpayment_rate"]                          * 0.35
        + _normalize(f["specialty_peer_deviation"], -3, 3)  * 0.25
        + f["high_value_cpt_ratio"]                         * 0.20
        + f["modifier_usage_rate"]                          * 0.12
        + f["same_day_multi_cpt_rate"]                      * 0.08
    ))


def _score_each_provider(
    df: pd.DataFrame,
    clf: RandomForestClassifier,
    scaler: StandardScaler,
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for npi in sorted(df["provider_npi"].unique()):
        mean_features = df[df["provider_npi"] == npi][FEATURE_COLS].mean()
        scaled = scaler.transform(mean_features.values.reshape(1, -1))
        try:
            prob = float(clf.predict_proba(scaled)[0][1])
        except Exception:
            prob = _formula_score(mean_features)
        scores[npi] = round(prob, 4)
    return scores


def _save_artifact(clf: RandomForestClassifier, scaler: StandardScaler) -> str:
    _ML_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    artifact = {"model": clf, "scaler": scaler, "feature_cols": FEATURE_COLS}
    with open(_ARTIFACT_PATH, "wb") as fh:
        pickle.dump(artifact, fh)
    return str(_ARTIFACT_PATH)


def load_model() -> tuple[RandomForestClassifier, StandardScaler]:
    """Load saved artifact. Returns (model, scaler)."""
    with open(_ARTIFACT_PATH, "rb") as fh:
        artifact = pickle.load(fh)
    return artifact["model"], artifact["scaler"]


# ---------------------------------------------------------------------------
# Main training function
# ---------------------------------------------------------------------------

def train_model(df: pd.DataFrame) -> dict[str, Any]:
    """
    Train the billing_variance_classifier on df.
    Returns a result dict containing provider_scores keyed by NPI.
    """
    X = df[FEATURE_COLS].values
    y = df[TARGET_COL].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    print(f"Training billing variance model...")
    print(f"Training rows: {len(df):,}")
    print(f"Method: sklearn_random_forest")

    clf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=1)
    cv_scores = cross_val_score(clf, X_scaled, y, cv=5, scoring="accuracy")
    clf.fit(X_scaled, y)

    model_artifact_id = _save_artifact(clf, scaler)
    provider_scores = _score_each_provider(df, clf, scaler)
    fi = dict(zip(FEATURE_COLS, clf.feature_importances_.tolist()))
    accuracy = float(cv_scores.mean())

    result: dict[str, Any] = {
        "success": True,
        "method": "sklearn_random_forest",
        "model_artifact_id": model_artifact_id,
        "accuracy": accuracy,
        "positive_rate": float(y.mean()),
        "training_rows": len(df),
        "feature_importance": fi,
        "provider_scores": provider_scores,
    }

    print(f"Accuracy: {accuracy:.3f}")
    print("Provider scores computed:")
    for npi, score in sorted(provider_scores.items()):
        print(f"  NPI {npi} → {score:.4f}")
    print("Model training complete.")

    return result


# ---------------------------------------------------------------------------
# DB write-back
# ---------------------------------------------------------------------------

def write_scores_to_db(provider_scores: dict[str, float]) -> int:
    """
    Write computed billing_variance_score to the providers table.
    Returns the number of rows updated.
    """
    db_path = os.getenv("DB_PATH", "./opa.db")
    updated = 0
    conn = sqlite3.connect(db_path)
    try:
        for npi, score in provider_scores.items():
            cursor = conn.execute(
                "UPDATE providers SET billing_variance_score = ? WHERE npi = ?",
                (score, npi),
            )
            updated += cursor.rowcount
        conn.commit()
    finally:
        conn.close()
    return updated


# ---------------------------------------------------------------------------
# Inference helper
# ---------------------------------------------------------------------------

def score_provider(features: dict[str, float]) -> float:
    """
    Score a single provider using the saved artifact.
    Returns predict_proba probability of overpayment (class 1).
    Falls back to weighted formula if artifact is not found.
    """
    try:
        clf, scaler = load_model()
        vals = np.array([[features[f] for f in FEATURE_COLS]], dtype=float)
        scaled = scaler.transform(vals)
        return float(clf.predict_proba(scaled)[0][1])
    except Exception:
        return _formula_score(pd.Series(features))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from app.ml.seed_training_data import generate_training_data, save_training_data

    df = generate_training_data()
    save_training_data(df)

    result = train_model(df)

    print(f"\nFeature importance:")
    fi = result["feature_importance"]
    for feat, imp in sorted(fi.items(), key=lambda x: -x[1]):
        print(f"  {feat:35s}  {imp:.4f}")

    n = write_scores_to_db(result["provider_scores"])
    print(f"\nUpdated {n} provider rows in opa.db")
