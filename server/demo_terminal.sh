#!/usr/bin/env bash
# Quick terminal test of the demo orchestrator: reseed a clean DB, then run the
# locked 10-file 835 set through the REAL pipeline in parallel. Temp dev helper.
set -e
cd "$(dirname "$0")"
VENV=../.venv/bin
echo "==> Reseeding clean demo DB (ML training, ~15s)..."
rm -f opa.db
$VENV/alembic upgrade head >/dev/null 2>&1
$VENV/python -m seed.seed_all >/dev/null 2>&1
echo "==> Running 10 uploaded 835s in parallel lanes..."
echo
$VENV/python _demo_run.py 2>&1 | grep -vE 'INFO|WARNING|Deprecat|warnings.warn'
