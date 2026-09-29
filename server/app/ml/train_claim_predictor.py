"""train_claim_predictor.py — Stage 2 Claim Predictor trainer.

Mirrors the provider pipeline (train_billing_variance): stratified split →
StandardScaler → SMOTE on the training fold → RandomForest → probability
calibration on a natural-ratio holdout. The output is a CALIBRATED per-claim
P(overpayment) — calibration matters because downstream EV multiplies this
probability by dollars, so it must read as a true frequency.

Two spec-specific rules (Stage 2 Feature Spec v1.3 §7):
  - Feature order is fixed: [P_risk, F4, F5, F7, F8].
  - StandardScaler is applied to F4/F5/F7 ONLY; P_risk (already 0-1) and F8
    (binary) pass through unscaled.

Public API:
    result = train_model(df)         # metrics + saves the artifact
    prob   = score_claim(features)   # dict {P_risk,F4,F5,F7,F8} -> float 0-1
"""
from __future__ import annotations

import json
import os
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    fbeta_score, roc_auc_score, brier_score_loss,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from imblearn.over_sampling import SMOTE

from .stage2_features import STAGE2_FEATURE_COLS, STAGE2_SCALED_COLS, TARGET_COL, REFERENCE_VERSION
from .train_billing_variance import _parse_max_features, _parse_class_weight

MODEL_NAME = "claim_predictor"
_ML_MODELS_DIR = Path(os.getenv("ML_MODELS_DIR", "./ml_models"))
_ARTIFACT_PATH = _ML_MODELS_DIR / f"{MODEL_NAME}.pkl"
# Spec's model_metadata.json — the last committed training's metrics/params, so
# the admin UI can show "current model" without retraining on every page load.
_META_PATH = _ML_MODELS_DIR / f"{MODEL_NAME}_meta.json"


def load_metadata() -> Optional[dict]:
    """Last committed Stage 2 training result (metrics + params), or None."""
    if not _META_PATH.exists():
        return None
    try:
        with open(_META_PATH) as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None

# Column positions of the scaled features within STAGE2_FEATURE_COLS order.
_SCALED_IDX = [STAGE2_FEATURE_COLS.index(c) for c in STAGE2_SCALED_COLS]


def _apply_scaler(X: np.ndarray, scaler: StandardScaler) -> np.ndarray:
    """Scale only the F4/F5/F7 columns; leave P_risk and F8 untouched."""
    X = np.asarray(X, dtype=float).copy()
    X[:, _SCALED_IDX] = scaler.transform(X[:, _SCALED_IDX])
    return X


# ── artifact ────────────────────────────────────────────────────────────────

def _save_artifact(clf: Any, scaler: StandardScaler, threshold: float, calibration: str) -> str:
    _ML_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    artifact = {
        "model": clf,                       # calibrated scorer (or raw RF if none)
        "scaler": scaler,                   # fit on F4/F5/F7 only
        "feature_cols": STAGE2_FEATURE_COLS,
        "scaled_cols": STAGE2_SCALED_COLS,
        "threshold": float(threshold),
        "calibration_method": calibration,
        "reference_version": REFERENCE_VERSION,
    }
    with open(_ARTIFACT_PATH, "wb") as fh:
        pickle.dump(artifact, fh)
    return str(_ARTIFACT_PATH)


def load_model() -> tuple[Any, StandardScaler]:
    with open(_ARTIFACT_PATH, "rb") as fh:
        artifact = pickle.load(fh)
    return artifact["model"], artifact["scaler"]


def artifact_exists() -> bool:
    return _ARTIFACT_PATH.exists()


# ── training ──────────────────────────────────────────────────────────────

def train_model(
    df: pd.DataFrame,
    *,
    n_estimators: int = 300,
    max_depth: Optional[int] = None,
    min_samples_split: int = 2,
    min_samples_leaf: int = 1,
    max_features: Optional[str] = "sqrt",
    max_leaf_nodes: Optional[int] = None,
    bootstrap: bool = True,
    class_weight: Optional[str] = None,
    criterion: str = "gini",
    decision_threshold_mode: str = "auto_f2",
    manual_threshold: Optional[float] = None,
    calibration_method: str = "sigmoid",
    persist_artifact: bool = True,
) -> dict[str, Any]:
    """Train the claim predictor on df (columns = STAGE2_FEATURE_COLS + target).

    Full RandomForest hyperparameter surface, mirroring the Stage 1 provider
    trainer. decision_threshold_mode: 'auto_f2' sweeps for the F2-optimal cutoff;
    'manual' pins manual_threshold."""
    X = df[STAGE2_FEATURE_COLS].values.astype(float)
    y = df[TARGET_COL].values.astype(int)

    X_trainfull, X_val, y_trainfull, y_val = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    # Calibration fold carved from training data at the natural ratio.
    cal = calibration_method if calibration_method in ("sigmoid", "isotonic") else "none"
    X_cal = y_cal = None
    if cal != "none":
        X_core, X_cal, y_core, y_cal = train_test_split(
            X_trainfull, y_trainfull, test_size=0.25, stratify=y_trainfull, random_state=42
        )
        if len(y_cal) < 12 or len(np.unique(y_cal)) < 2:
            X_core, y_core, X_cal, y_cal, cal = X_trainfull, y_trainfull, None, None, "none"
    else:
        X_core, y_core = X_trainfull, y_trainfull

    # Scaler fit on the F4/F5/F7 columns of the CORE training fold only.
    scaler = StandardScaler().fit(X_core[:, _SCALED_IDX])
    X_core_s = _apply_scaler(X_core, scaler)
    X_val_s = _apply_scaler(X_val, scaler)

    # SMOTE the scaled core fold to 50/50; validation/calibration stay natural.
    try:
        X_bal, y_bal = SMOTE(random_state=42).fit_resample(X_core_s, y_core)
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] SMOTE skipped ({exc}); training on natural ratio")
        X_bal, y_bal = X_core_s, y_core

    clf = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_split=min_samples_split,
        min_samples_leaf=min_samples_leaf,
        max_features=_parse_max_features(max_features),
        max_leaf_nodes=max_leaf_nodes,
        bootstrap=bootstrap,
        class_weight=_parse_class_weight(class_weight),
        criterion=criterion,
        random_state=42, n_jobs=1,
    )
    clf.fit(X_bal, y_bal)

    proba_raw = clf.predict_proba(X_val_s)[:, 1]
    if cal != "none":
        scoring_model: Any = CalibratedClassifierCV(FrozenEstimator(clf), method=cal)
        scoring_model.fit(_apply_scaler(X_cal, scaler), y_cal)
    else:
        scoring_model = clf
    proba_val = scoring_model.predict_proba(X_val_s)[:, 1]

    auc = float(roc_auc_score(y_val, proba_val))
    brier_raw = float(brier_score_loss(y_val, proba_raw))
    brier_cal = float(brier_score_loss(y_val, proba_val))

    # Threshold: manual pin, else F2-optimal sweep (recall-leaning).
    if decision_threshold_mode == "manual" and manual_threshold is not None:
        best_thr = float(manual_threshold)
        best_f2 = float(fbeta_score(y_val, (proba_val >= best_thr).astype(int), beta=2.0, zero_division=0))
    else:
        best_f2, best_thr = -1.0, 0.5
        for t in np.linspace(0.05, 0.95, 91):
            f2 = float(fbeta_score(y_val, (proba_val >= t).astype(int), beta=2.0, zero_division=0))
            if f2 > best_f2:
                best_f2, best_thr = f2, float(t)

    pred = (proba_val >= best_thr).astype(int)
    artifact_id = (
        _save_artifact(scoring_model, scaler, best_thr, cal) if persist_artifact else "trial"
    )

    result = {
        "success": True,
        "model_name": MODEL_NAME,
        "model_artifact_id": artifact_id,
        "params": {
            "n_estimators": int(n_estimators), "max_depth": max_depth,
            "min_samples_split": int(min_samples_split), "min_samples_leaf": int(min_samples_leaf),
            "max_features": max_features, "max_leaf_nodes": max_leaf_nodes,
            "bootstrap": bool(bootstrap), "class_weight": class_weight, "criterion": criterion,
            "decision_threshold_mode": decision_threshold_mode, "manual_threshold": manual_threshold,
            "calibration_method": calibration_method,
        },
        "features": STAGE2_FEATURE_COLS,
        "feature_importance": dict(zip(STAGE2_FEATURE_COLS, clf.feature_importances_.tolist())),
        "accuracy": float(accuracy_score(y_val, pred)),
        "precision": float(precision_score(y_val, pred, zero_division=0)),
        "recall": float(recall_score(y_val, pred, zero_division=0)),
        "f1_score": float(f1_score(y_val, pred, zero_division=0)),
        "f2_score": best_f2,
        "auc_roc": auc,
        "threshold": best_thr,
        "calibration_method": cal,
        "brier_raw": brier_raw,
        "brier_calibrated": brier_cal,
        "positive_rate": float(y.mean()),
        "training_rows": int(len(df)),
    }
    if persist_artifact:
        result["trained_at"] = datetime.utcnow().isoformat()
        try:
            _ML_MODELS_DIR.mkdir(parents=True, exist_ok=True)
            with open(_META_PATH, "w") as fh:
                json.dump(result, fh)
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] could not write metadata ({exc})")

    print(f"Stage 2 claim predictor trained: rows={len(df):,} pos_rate={y.mean():.3f} "
          f"AUC={auc:.3f} F2={best_f2:.3f} thr={best_thr:.2f} "
          f"Brier {brier_raw:.4f}->{brier_cal:.4f} cal={cal}")
    print(f"  feature importance: "
          + ", ".join(f"{k}={v:.3f}" for k, v in result['feature_importance'].items()))
    return result


# ── inference ─────────────────────────────────────────────────────────────

def score_claim(features: dict[str, float]) -> float:
    """Calibrated P(overpayment) for one claim's feature dict. Returns P_risk as
    a safe fallback if the artifact is missing (model unavailable)."""
    try:
        clf, scaler = load_model()
    except FileNotFoundError:
        return float(features.get("P_risk", 0.5))
    vec = np.array([[float(features[c]) for c in STAGE2_FEATURE_COLS]], dtype=float)
    vec = _apply_scaler(vec, scaler)
    return float(clf.predict_proba(vec)[0][1])


if __name__ == "__main__":
    from app.ml.seed_stage2_training_data import generate_training_data
    train_model(generate_training_data())
