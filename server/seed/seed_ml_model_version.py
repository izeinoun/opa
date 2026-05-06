"""Seed MLModelVersion — synchronous sqlite3.

Reads the training result from the saved artifact (if present) or uses
the known default values from the sklearn fallback training run.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW = "2024-01-15T08:30:00"

# Default values matching the sklearn fallback training run results
_DEFAULT_RESULT = {
    "model_name":        "billing_variance_classifier",
    "model_artifact_id": str(Path(os.getenv("ML_MODELS_DIR", "./ml_models"))
                             / "billing_variance_classifier.pkl"),
    "trained_at":        NOW,
    "training_rows":     5000,
    "training_window":   "12_months_synthetic",
    "accuracy":          0.760,
    "positive_rate":     0.230,
    "feature_importance": {
        "prior_overpayment_rate":    0.28,
        "specialty_peer_deviation":  0.22,
        "high_value_cpt_ratio":      0.17,
        "modifier_usage_rate":       0.12,
        "same_day_multi_cpt_rate":   0.09,
        "multi_line_claim_ratio":    0.07,
        "avg_units_per_line":        0.05,
    },
    "is_active":    True,
    "notes":        "sklearn_fallback; Penguin FDEAutoML not installed in this environment",
}


def _load_artifact_result() -> dict:
    """Try to read training metadata from the pkl artifact."""
    try:
        import pickle
        artifact_path = Path(os.getenv("ML_MODELS_DIR", "./ml_models")) / "billing_variance_classifier.pkl"
        if not artifact_path.exists():
            return _DEFAULT_RESULT
        with open(artifact_path, "rb") as fh:
            artifact = pickle.load(fh)
        # artifact is {"model": clf, "scaler": scaler, "feature_cols": [...]}
        # Extract feature importance if available
        clf = artifact.get("model")
        fi_dict = _DEFAULT_RESULT["feature_importance"].copy()
        if hasattr(clf, "feature_importances_"):
            cols = artifact.get("feature_cols", list(fi_dict.keys()))
            fi_dict = dict(zip(cols, [round(float(v), 4) for v in clf.feature_importances_]))
        result = _DEFAULT_RESULT.copy()
        result["feature_importance"] = fi_dict
        return result
    except Exception:
        return _DEFAULT_RESULT


def run(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    try:
        if conn.execute("SELECT COUNT(*) FROM ml_model_versions").fetchone()[0]:
            print("  ml_model_versions already seeded — skipping")
            return

        r = _load_artifact_result()

        conn.execute(
            "INSERT INTO ml_model_versions "
            "(version_id, model_name, model_artifact_id, trained_at, training_rows, "
            "training_window, accuracy, positive_rate, feature_importance, "
            "is_active, notes, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(uuid4()),
                r["model_name"],
                r["model_artifact_id"],
                r["trained_at"],
                r["training_rows"],
                r["training_window"],
                r["accuracy"],
                r["positive_rate"],
                json.dumps(r["feature_importance"]),
                1 if r["is_active"] else 0,
                r["notes"],
                NOW,
            ),
        )
        conn.commit()
        print(f"  Inserted ML model version: {r['model_name']} accuracy={r['accuracy']:.3f}")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
