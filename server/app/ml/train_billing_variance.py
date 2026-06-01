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
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

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

_DEFAULT_PARAMS: dict[str, Any] = {
    "n_estimators": 200,
    "max_depth": None,                  # sklearn default = unlimited
    "min_samples_split": 2,             # sklearn default
    "min_samples_leaf": 1,              # sklearn default
    "max_features": "sqrt",             # sklearn classifier default
    "max_leaf_nodes": None,             # sklearn default = unlimited
    "bootstrap": True,                  # sklearn default
    "class_weight": None,               # sklearn default
    "criterion": "gini",                # sklearn default
    "decision_threshold_mode": "auto_f2",
    "manual_threshold": None,
}


def _resolve_params(params: Optional[dict] = None) -> dict[str, Any]:
    """Fill missing keys with defaults so callers can pass partial dicts."""
    merged = dict(_DEFAULT_PARAMS)
    if params:
        for k, v in params.items():
            if k in merged:
                merged[k] = v
    return merged


def _parse_max_features(value: Any) -> Any:
    """Map the stored/string form of max_features onto what sklearn accepts.

    'none'/None/'' → None (use all features); 'sqrt'/'log2' pass through;
    a numeric string → float fraction; anything else falls back to 'sqrt'.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    v = str(value).strip().lower()
    if v in ("", "none", "all"):
        return None
    if v in ("sqrt", "log2"):
        return v
    try:
        return float(v)
    except ValueError:
        return "sqrt"


def _parse_class_weight(value: Any) -> Any:
    """'none'/None/'' → None; 'balanced'/'balanced_subsample' pass through."""
    if value is None:
        return None
    v = str(value).strip().lower()
    if v in ("", "none"):
        return None
    if v in ("balanced", "balanced_subsample"):
        return v
    return None


def train_model(
    df: pd.DataFrame,
    params: Optional[dict] = None,
    *,
    persist_artifact: bool = True,
) -> dict[str, Any]:
    """
    Train the billing_variance_classifier on df.

    Hyperparameters come from `params` (typically loaded from ml_training_config);
    missing keys fall back to _DEFAULT_PARAMS. Currently honored:
      n_estimators, max_depth, min_samples_leaf, decision_threshold_mode,
      manual_threshold.

    Pipeline:
      1. Stratified 80/20 train/validation split
      2. StandardScaler fit on the training fold only
      3. SMOTE oversampling on the training fold only (50/50 balance);
         validation remains at the natural class ratio so metrics are honest
      4. RandomForest training with the resolved hyperparameters
      5. Threshold selection:
           mode='auto_f2' → sweep [0.05, 0.95] and pick the F2-maximizing cutoff
           mode='manual'  → use params['manual_threshold'] verbatim
      6. AUC-ROC computed on raw probabilities (threshold-agnostic)

    Returns a result dict including precision, recall, F1, F2, AUC-ROC, the
    chosen threshold, and per-provider raw probabilities.
    """
    p = _resolve_params(params)

    X = df[FEATURE_COLS].values
    y = df[TARGET_COL].values

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_val_s   = scaler.transform(X_val)

    smote = SMOTE(random_state=42)
    X_train_bal, y_train_bal = smote.fit_resample(X_train_s, y_train)
    train_pos = int(y_train_bal.sum())
    train_total = int(len(y_train_bal))

    print(f"Training billing variance model...")
    print(f"  Training rows (raw)        : {len(df):,}")
    print(f"  Training fold (post-SMOTE) : {train_total:,}  ({train_pos:,} positive)")
    print(f"  Validation fold            : {len(y_val):,}  ({int(y_val.sum()):,} positive)")
    print(f"  Params                     : n_estimators={p['n_estimators']} "
          f"max_depth={p['max_depth']} min_samples_split={p['min_samples_split']} "
          f"min_samples_leaf={p['min_samples_leaf']} max_features={p['max_features']} "
          f"max_leaf_nodes={p['max_leaf_nodes']} bootstrap={p['bootstrap']} "
          f"class_weight={p['class_weight']} criterion={p['criterion']} "
          f"threshold_mode={p['decision_threshold_mode']}")

    clf = RandomForestClassifier(
        n_estimators=p["n_estimators"],
        max_depth=p["max_depth"],
        min_samples_split=p["min_samples_split"],
        min_samples_leaf=p["min_samples_leaf"],
        max_features=_parse_max_features(p["max_features"]),
        max_leaf_nodes=p["max_leaf_nodes"],
        bootstrap=p["bootstrap"],
        class_weight=_parse_class_weight(p["class_weight"]),
        criterion=p["criterion"],
        random_state=42,
        n_jobs=1,
    )
    clf.fit(X_train_bal, y_train_bal)

    proba_val = clf.predict_proba(X_val_s)[:, 1]
    auc = float(roc_auc_score(y_val, proba_val))

    # Threshold selection
    if p["decision_threshold_mode"] == "manual" and p["manual_threshold"] is not None:
        best_thr = float(p["manual_threshold"])
        pred_at_thr = (proba_val >= best_thr).astype(int)
        best_f2 = float(fbeta_score(y_val, pred_at_thr, beta=2.0, zero_division=0))
    else:
        best_f2 = -1.0
        best_thr = 0.5
        for t in np.linspace(0.05, 0.95, 91):
            pred = (proba_val >= t).astype(int)
            f2 = float(fbeta_score(y_val, pred, beta=2.0, zero_division=0))
            if f2 > best_f2:
                best_f2 = f2
                best_thr = float(t)

    pred_val = (proba_val >= best_thr).astype(int)
    accuracy  = float(accuracy_score(y_val, pred_val))
    precision = float(precision_score(y_val, pred_val, zero_division=0))
    recall    = float(recall_score(y_val, pred_val, zero_division=0))
    f1        = float(f1_score(y_val, pred_val, zero_division=0))

    # Trial runs (persist_artifact=False) must not clobber the live .pkl; they
    # only need the metrics and provider scores for the engineer to inspect.
    model_artifact_id = _save_artifact(clf, scaler, threshold=best_thr) if persist_artifact else "trial"
    provider_scores = _score_each_provider(df, clf, scaler)
    fi = dict(zip(FEATURE_COLS, clf.feature_importances_.tolist()))

    result: dict[str, Any] = {
        "success": True,
        "method": "sklearn_random_forest_smote_f2",
        "model_name": MODEL_NAME,
        "model_artifact_id": model_artifact_id,
        "params_used": p,
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

def read_training_config_sync(db_path: Optional[str] = None) -> dict[str, Any]:
    """Sync read of ml_training_config.current. Returns a params dict suitable
    for train_model(). If the row is missing or the table doesn't exist yet,
    returns the defaults — train_model() will still run."""
    db_path = db_path or os.getenv("DB_PATH", "./opa.db")
    conn = sqlite3.connect(db_path)
    try:
        try:
            row = conn.execute(
                "SELECT n_estimators, max_depth, min_samples_split, min_samples_leaf, "
                "max_features, max_leaf_nodes, bootstrap, class_weight, criterion, "
                "decision_threshold_mode, manual_threshold "
                "FROM ml_training_config WHERE config_id = 'current'"
            ).fetchone()
        except sqlite3.OperationalError:
            return dict(_DEFAULT_PARAMS)
        if not row:
            return dict(_DEFAULT_PARAMS)
        return {
            "n_estimators": row[0],
            "max_depth": row[1],
            "min_samples_split": row[2],
            "min_samples_leaf": row[3],
            "max_features": row[4],
            "max_leaf_nodes": row[5],
            "bootstrap": bool(row[6]),
            "class_weight": row[7],
            "criterion": row[8],
            "decision_threshold_mode": row[9],
            "manual_threshold": row[10],
        }
    finally:
        conn.close()


def write_version_to_db_sync(
    result: dict[str, Any],
    params: dict[str, Any],
    *,
    db_path: Optional[str] = None,
    training_window: str = "12_months",
    notes: str = "",
) -> str:
    """Sync insert into ml_model_versions from a trainer result dict.

    Honors the min_auc_to_promote gate on ml_training_config when present.
    Returns the new version_id.
    """
    import json as _json
    db_path = db_path or os.getenv("DB_PATH", "./opa.db")
    conn = sqlite3.connect(db_path)
    try:
        # Promotion gate
        promote = True
        try:
            gate = conn.execute(
                "SELECT min_auc_to_promote FROM ml_training_config WHERE config_id='current'"
            ).fetchone()
            auc = result.get("auc_roc")
            if gate and gate[0] is not None and auc is not None and auc < gate[0]:
                promote = False
        except sqlite3.OperationalError:
            pass

        if promote:
            conn.execute("UPDATE ml_model_versions SET is_active = 0")

        version_id = str(uuid4())
        conn.execute(
            "INSERT INTO ml_model_versions ("
            "version_id, model_name, model_artifact_id, trained_at, training_rows, "
            "training_window, training_params, accuracy, precision_score, recall_score, "
            "f1_score, f2_score, auc_roc, decision_threshold, positive_rate, "
            "feature_importance, is_active, notes, created_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                version_id,
                result.get("model_name", MODEL_NAME),
                result.get("model_artifact_id", ""),
                datetime.utcnow().isoformat(),
                result.get("training_rows", 0),
                training_window,
                _json.dumps(params),
                result.get("accuracy", 0.0),
                result.get("precision"),
                result.get("recall"),
                result.get("f1_score"),
                result.get("f2_score"),
                result.get("auc_roc"),
                result.get("threshold"),
                result.get("positive_rate", 0.0),
                _json.dumps(result.get("feature_importance", {})),
                1 if promote else 0,
                notes,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        return version_id
    finally:
        conn.close()


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
