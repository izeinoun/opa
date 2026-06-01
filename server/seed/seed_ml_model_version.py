"""Seed the ml_training_config singleton.

Previously this file inserted a stub ml_model_versions row with synthetic
metrics. That responsibility now belongs to the trainer itself
(train_billing_variance.write_version_to_db_sync), which runs during
seed_all step 8 and produces a real, full-metric row.

What this file does now:
  • Ensure the ml_training_config singleton exists with default values
    matching the live trainer defaults. The admin UI edits this row;
    train_model() reads it on every subsequent training run.

Kept under the same filename so seed_all.py's import path is stable.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "./opa.db")


def run(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    try:
        existing = conn.execute(
            "SELECT COUNT(*) FROM ml_training_config WHERE config_id = 'current'"
        ).fetchone()[0]
        if existing:
            print("  ml_training_config already seeded — skipping")
            return

        # Values mirror train_billing_variance._DEFAULT_PARAMS so the seeded
        # config reproduces the trainer's out-of-the-box RandomForest behavior.
        # All NOT NULL columns must be listed explicitly — create_all builds the
        # table with no SQL-level DEFAULTs (the model uses ORM-side `default=`).
        conn.execute(
            "INSERT INTO ml_training_config ("
            "config_id, n_estimators, max_depth, min_samples_split, min_samples_leaf, "
            "max_features, max_leaf_nodes, bootstrap, class_weight, criterion, "
            "decision_threshold_mode, manual_threshold, min_auc_to_promote, updated_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "current",
                200,            # n_estimators — previously hardcoded value
                None,           # max_depth — sklearn default (unlimited)
                2,              # min_samples_split — sklearn default
                1,              # min_samples_leaf — sklearn default
                "sqrt",         # max_features — sklearn classifier default
                None,           # max_leaf_nodes — sklearn default (unlimited)
                1,              # bootstrap — sklearn default (True)
                None,           # class_weight — sklearn default (none)
                "gini",         # criterion — sklearn default
                "auto_f2",      # decision_threshold_mode — F2-tuned sweep
                None,           # manual_threshold
                None,           # min_auc_to_promote
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        print("  Seeded ml_training_config singleton (defaults)")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
