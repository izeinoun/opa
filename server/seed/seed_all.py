"""Master seed runner — executes all seeds in dependency order.

Usage (from /server directory):
    python -m seed.seed_all
    DB_PATH=./opa.db python -m seed.seed_all

Order:
  Step  1/11 — seed_users
  Step  2/11 — seed_providers       (billing_variance_score=0.5 initially)
  Step  3/11 — seed_codes
  Step  4/11 — seed_fee_schedules
  Step  5/11 — seed_members
  Step  6/11 — seed_reference_freshness
  Step  7/11 — seed_letter_templates
  Step  8/11 — ML training           (overwrites billing_variance_score,
                                      writes ml_model_versions row)
  Step  9/11 — seed_ml_training_config  (admin-editable RF hyperparams)
  Step 10/11 — seed_demo_cases      (15 demo claims, real detector runs,
                                     dates relative to TODAY)
  Step 11/11 — summary
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path

# Ensure /server is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = os.getenv("DB_PATH", "./opa.db")


def _count(table: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        # Stale/absent table in the summary list shouldn't crash the seed run.
        return -1
    finally:
        conn.close()


def _step(n: int, total: int, name: str) -> None:
    print(f"\n[Step {n:2d}/{total}] {name}")
    print("─" * 50)


def _run_ml_training() -> None:
    """Run ML training, write provider scores, and persist the resulting
    ml_model_versions row with the resolved hyperparameters."""
    try:
        from app.ml.seed_training_data import generate_training_data
        from app.ml.train_billing_variance import (
            train_model,
            write_scores_to_db,
            read_training_config_sync,
            write_version_to_db_sync,
        )

        params = read_training_config_sync(DB_PATH)
        df = generate_training_data()
        result = train_model(df, params=params)
        n_updated = write_scores_to_db(result["provider_scores"])
        version_id = write_version_to_db_sync(
            result, params, db_path=DB_PATH, training_window="12_months_synthetic"
        )
        print(f"  ML training complete: {result['method']} | "
              f"accuracy={result['accuracy']:.3f} auc={result.get('auc_roc', 0):.3f} | "
              f"updated {n_updated} provider scores | version={version_id[:8]}")
    except Exception as exc:
        print(f"  ML training failed ({exc}); providers retain billing_variance_score=0.5")


def main() -> None:
    total = 11
    t0 = time.time()

    _step(1, total, "seed_users")
    from seed.seed_users import run as seed_users
    seed_users(DB_PATH)

    _step(2, total, "seed_providers  (billing_variance_score=0.5)")
    from seed.seed_providers import run as seed_providers
    seed_providers(DB_PATH)

    print()
    print("[Step 2b] seed_excluded_providers  (CMS/OIG LEIE — DET-08 NPI screen)")
    print("─" * 50)
    from seed.seed_excluded_providers import run as seed_excluded
    seed_excluded(DB_PATH)

    _step(3, total, "seed_codes")
    from seed.seed_codes import run as seed_codes
    seed_codes(DB_PATH)

    _step(3, total, "seed_inpatient_icd  (25 inpatient ICD-10 codes)")
    from seed.seed_inpatient_icd import run as seed_inpatient_icd
    seed_inpatient_icd(DB_PATH)

    _step(3, total, "seed_extended_icd  (85 codes across all care settings)")
    from seed.seed_extended_icd import run as seed_extended_icd
    seed_extended_icd(DB_PATH)

    _step(3, total, "seed_extended_cpt  (43 CPT/HCPCS codes with dx-coverage and modifier map)")
    from seed.seed_extended_cpt import run as seed_extended_cpt
    seed_extended_cpt(DB_PATH)

    _step(3, total, "seed_extended_drg  (47 MS-DRG codes with triplet links)")
    from seed.seed_extended_drg import run as seed_extended_drg
    seed_extended_drg(DB_PATH)

    _step(3, total, "seed_bill_revenue_codes  (19 bill types, 70 revenue codes)")
    from seed.seed_bill_revenue_codes import run as seed_bill_revenue_codes
    seed_bill_revenue_codes(DB_PATH)

    _step(4, total, "seed_fee_schedules")
    from seed.seed_fee_schedules import run as seed_fee_schedules
    seed_fee_schedules(DB_PATH)

    _step(5, total, "seed_members")
    from seed.seed_members import run as seed_members
    seed_members(DB_PATH)

    print()
    print("[Step 5b] seed_clearlink_sync  (ClearLink members/providers for MCP testing)")
    print("─" * 50)
    from seed.seed_clearlink_sync import run as seed_clearlink
    seed_clearlink(DB_PATH)

    _step(6, total, "seed_reference_freshness")
    from seed.seed_reference_freshness import run as seed_ref
    seed_ref(DB_PATH)

    _step(7, total, "seed_letter_templates")
    from seed.seed_letter_templates import run as seed_templates
    seed_templates(DB_PATH)

    print()
    print("[Step 7b] seed_evidence_requirements")
    print("─" * 50)
    from seed.seed_evidence_requirements import run as seed_evidence
    seed_evidence(DB_PATH)

    print()
    print("[Step 7c] seed_rbac (apps, roles, role_apps, backfill user_roles)")
    print("─" * 50)
    from seed.seed_rbac import run as seed_rbac
    seed_rbac(DB_PATH)

    print()
    print("[Step 7d] seed_code_evidence_requirements  (ICD/DRG → evidence rules)")
    print("─" * 50)
    from seed.seed_code_evidence_requirements import run as seed_code_evid
    seed_code_evid(DB_PATH)

    print()
    print("[Step 7e] seed_document_templates  (generic LLM doc templates per app)")
    print("─" * 50)
    from seed.seed_document_templates import run as seed_doc_templates
    seed_doc_templates(DB_PATH)

    print()
    print("[Step 7f] seed_rule_prompts  (LLM prompts for DET-09, DET-18, FWA-02, FWA-03)")
    print("─" * 50)
    from seed.seed_rule_prompts import seed as seed_rule_prompts
    seed_rule_prompts(DB_PATH)

    _step(8, total, "ML training  (billing_variance_score overwrite)")
    _run_ml_training()

    _step(9, total, "seed_ml_training_config")
    from seed.seed_ml_model_version import run as seed_ml_version
    seed_ml_version(DB_PATH)

    _step(10, total, "seed_demo_cases  (15 claims, real detectors, relative dates)")
    from seed.seed_demo_cases import run as seed_demo
    seed_demo(DB_PATH)

    print()
    print("[Step 10b] seed_prepay_claims  (ClaimGuard pre-pay AI-findings demo)")
    print("─" * 50)
    from seed.seed_prepay_claims import run as seed_prepay
    seed_prepay(DB_PATH)

    print()
    print("[Step 10c] seed_runtime_config  (feature flags)")
    print("─" * 50)
    import sqlite3 as _sqlite3
    _conn = _sqlite3.connect(DB_PATH)
    _conn.execute(
        "INSERT OR IGNORE INTO runtime_config (key, value, updated_at) VALUES (?, ?, ?)",
        ("ai_suggestions_enabled", "false", __import__("datetime").datetime.utcnow().isoformat()),
    )
    _conn.commit()
    _conn.close()
    print("[seed_runtime_config] ai_suggestions_enabled = false (enable via Admin → Runtime Config)")

    print()
    print("[Step 10d] seed_ana_performance  (Dashboard demo data for Ana Chen)")
    print("─" * 50)
    from seed.seed_ana_performance import run as seed_ana_perf
    seed_ana_perf(DB_PATH)

    print()
    print("[Step 10e] seed_hmo_contract  (HMO contract with carve-outs)")
    print("─" * 50)
    from seed.seed_hmo_contract import run as seed_hmo_contract
    seed_hmo_contract(DB_PATH)

    print()
    print("[Step 10f] seed_carveout_violation_claims  (Pre-pay claims for DET-20)")
    print("─" * 50)
    from seed.seed_carveout_violation_claims import run as seed_carveout_claims
    seed_carveout_claims(DB_PATH)

    elapsed = time.time() - t0

    # ── Summary table ─────────────────────────────────────────────────────
    print(f"\n{'─' * 50}")
    print(f"[Step 11/{total}] Summary")
    print(f"{'─' * 50}")
    TABLE_COUNTS = [
        ("opa_users",               "Users"),
        ("provider_orgs",           "Provider Orgs"),
        ("providers",               "Providers"),
        ("cpt_codes",               "CPT Codes"),
        ("icd_codes",               "ICD Codes"),
        ("cpt_dx_coverage",         "CPT-DX Coverage Rules"),
        ("excluded_providers",      "Excluded Providers (OIG LEIE)"),
        ("fee_schedules",           "Fee Schedule Rows"),
        ("contract_limitations",    "Contract Limitations"),
        ("members",                 "Members"),
        ("reference_data_freshness","Reference Freshness"),
        ("letter_templates",        "Letter Templates"),
        ("claims",                  "Claims"),
        ("claim_lines",             "Claim Lines"),
        ("case_groups",             "Case Groups"),
        ("transactions_835",        "ERA Transactions"),
        ("claim_payments_835",      "ERA Claim Payments"),
        ("opa_cases",               "Cases"),
        ("findings",                "Findings"),
        ("case_findings",           "Case-Finding Links"),
        ("likelihood_scores",       "Likelihood Scores"),
        ("audit_logs",              "Audit Log Entries"),
        ("disputes",                "Disputes"),
        ("provider_notices",        "Provider Notices"),
        ("recoupment_actions",      "Recoupment Actions"),
        ("reconciliations",         "Reconciliations"),
        ("ml_model_versions",       "ML Model Versions"),
    ]

    print(f"  {'Table':<30} {'Rows':>8}")
    print(f"  {'─' * 30} {'─' * 8}")
    total_rows = 0
    for table, label in TABLE_COUNTS:
        n = _count(table)
        total_rows += n
        print(f"  {label:<30} {n:>8,}")

    print(f"  {'─' * 30} {'─' * 8}")
    print(f"  {'TOTAL':<30} {total_rows:>8,}")
    print(f"\n  Completed in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
