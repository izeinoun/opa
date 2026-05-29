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

        conn.execute(
            "INSERT INTO ml_training_config ("
            "config_id, n_estimators, max_depth, min_samples_leaf, "
            "decision_threshold_mode, manual_threshold, min_auc_to_promote, updated_at"
            ") VALUES (?,?,?,?,?,?,?,?)",
            (
                "current",
                200,            # matches the previously hardcoded n_estimators
                None,           # sklearn default — unlimited depth
                1,              # sklearn default
                "auto_f2",      # preserves the F2-tuned threshold sweep
                None,
                None,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        print("  Seeded ml_training_config singleton (defaults)")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
