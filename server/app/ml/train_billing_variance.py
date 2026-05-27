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
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score,
    f1_score, fbeta_score, roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from imblearn.over_sampling import SMOTE

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
    """Weighted heuristic score used when the saved artifact is absent.

    Uses all 7 features (matching FEATURE_COLS). Weights sum to 1.0.
    Range guards: specialty_peer_deviation is a z-score (~[-3, 3]) and
    avg_units_per_line is a count (~[1, 6]); both normalized to [0, 1]
    before weighting.
    """
    f = features
    return min(1.0, (
        f["prior_overpayment_rate"]                            * 0.30
        + _normalize(f["specialty_peer_deviation"], -3, 3)    * 0.22
        + f["high_value_cpt_ratio"]                           * 0.17
        + f["modifier_usage_rate"]                            * 0.10
        + f["same_day_multi_cpt_rate"]                        * 0.07
        + _normalize(f["avg_units_per_line"], 1, 6)           * 0.08
        + f["multi_line_claim_ratio"]                         * 0.06
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


def _save_artifact(
    clf: RandomForestClassifier, scaler: StandardScaler, threshold: float = 0.5,
) -> str:
    _ML_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    artifact = {
        "model": clf,
        "scaler": scaler,
        "feature_cols": FEATURE_COLS,
        "threshold": float(threshold),  # F2-optimal cutoff for binary verdict
    }
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

    Pipeline:
      1. Stratified 80/20 train/validation split
      2. StandardScaler fit on the training fold only
      3. SMOTE oversampling on the training fold only (50/50 balance);
         validation remains at the natural class ratio so metrics are honest
      4. RandomForest training
      5. Threshold tuning on validation by maximizing F2 (recall-weighted);
         the tuned threshold is stored in the artifact for downstream callers
         that need a binary verdict
      6. AUC-ROC computed on raw probabilities (threshold-agnostic)

    Returns a result dict including precision, recall, F1, F2, AUC-ROC, and
    the per-provider raw probabilities (production uses the raw probability
    as a Bayesian prior — the threshold only matters for the binary verdict).
    """
    X = df[FEATURE_COLS].values
    y = df[TARGET_COL].values

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    # Fit the scaler on training only (no leakage)
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_val_s   = scaler.transform(X_val)

    # SMOTE on training fold only
    smote = SMOTE(random_state=42)
    X_train_bal, y_train_bal = smote.fit_resample(X_train_s, y_train)
    train_pos = int(y_train_bal.sum())
    train_total = int(len(y_train_bal))

    print(f"Training billing variance model...")
    print(f"  Training rows (raw)        : {len(df):,}")
    print(f"  Training fold (post-SMOTE) : {train_total:,}  ({train_pos:,} positive)")
    print(f"  Validation fold            : {len(y_val):,}  ({int(y_val.sum()):,} positive)")
    print(f"  Method                     : sklearn_random_forest + SMOTE + F2-tuned threshold")

    clf = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=1)
    clf.fit(X_train_bal, y_train_bal)

    # Validation probabilities
    proba_val = clf.predict_proba(X_val_s)[:, 1]
    auc = float(roc_auc_score(y_val, proba_val))

    # Sweep thresholds and pick the one that maximizes F2
    best_f2 = -1.0
    best_thr = 0.5
    for t in np.linspace(0.05, 0.95, 91):
        pred = (proba_val >= t).astype(int)
        f2 = float(fbeta_score(y_val, pred, beta=2.0, zero_division=0))
        if f2 > best_f2:
            best_f2 = f2
            best_thr = float(t)

    # Final metrics at the chosen threshold
    pred_val = (proba_val >= best_thr).astype(int)
    accuracy  = float(accuracy_score(y_val, pred_val))
    precision = float(precision_score(y_val, pred_val, zero_division=0))
    recall    = float(recall_score(y_val, pred_val, zero_division=0))
    f1        = float(f1_score(y_val, pred_val, zero_division=0))

    model_artifact_id = _save_artifact(clf, scaler, threshold=best_thr)
    provider_scores = _score_each_provider(df, clf, scaler)
    fi = dict(zip(FEATURE_COLS, clf.feature_importances_.tolist()))

    result: dict[str, Any] = {
        "success": True,
        "method": "sklearn_random_forest_smote_f2",
        "model_artifact_id": model_artifact_id,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "f2_score": best_f2,
        "auc_roc": auc,
        "threshold": best_thr,
        "positive_rate": float(y.mean()),
        "training_rows": len(df),
        "feature_importance": fi,
        "provider_scores": provider_scores,
    }

    print(f"\nValidation metrics @ F2-optimal threshold {best_thr:.2f}:")
    print(f"  Accuracy  : {accuracy*100:5.1f}%")
    print(f"  Precision : {precision*100:5.1f}%")
    print(f"  Recall    : {recall*100:5.1f}%")
    print(f"  F1        : {f1*100:5.1f}%")
    print(f"  F2        : {best_f2*100:5.1f}%")
    print(f"  AUC-ROC   : {auc*100:5.1f}%")

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
