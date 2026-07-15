# CLAUDE.md

Guidance for Claude Code when working in this repository. **Verified against code 2026-06-29.** When in doubt, trust the code over any prose — known drift is called out inline.

## ⭐ Suite context map — read first for cross-project work

This repo (OPA / PayGuard) is the **hub backend** for an 8-project suite. A dense, machine-readable map of the whole suite lives at **`docs/codebase-map/INDEX.md`** — per-project profiles, dependency graph, MCP inventory, data-model ownership, reuse map, and a live-bug hotlist. Use it before debugging across services, tracing a request, or adding a feature. Active remediation roadmap: `docs/codebase-map/ACTION-PLAN.md`.

Suite shape: OPA backend (FastAPI `:8001`) is the single backend; 5 React SPAs (claimguard:5175, iam:5177, siu:5178, assistant:5179, intake-portal:5181) are thin clients of it; **ClearLink** (Node `:8010`) is a second backend OPA calls via MCP `/mcp` + REST; mock-provider-portal (`:3002`) is a Playwright target. Prod = `*.penguinai.studio`, OPA = `payguard.penguinai.studio`.

## Commands

All `make` targets run from the repo root (`opa/`).

```bash
make setup     # pip install server reqs, npm install client, alembic upgrade head
make seed      # run server/seed/seed_all.py (includes ML training); creates demo cases
make dev       # backend + frontend; backend :8001, frontend :5174
make backend   # backend only (uvicorn --reload --port 8001)
make frontend  # frontend only (vite, :5174)
make verify    # python verify_env.py — checks env vars
make test      # cd server && pytest tests/ -v
make health    # curl :8001/health
make clean     # wipe opa.db, ml_models/, __pycache__
```

### Python environment

**No venv inside `opa/`.** Shared venv at the parent path: `/Users/issamzeinoun/claude/overcoding/.venv`. `uvicorn`, `pytest`, etc. are not on the system PATH — use that venv's `bin/` directly or activate it first. `make` targets call `uvicorn` unqualified and fail unless the venv is active/on PATH.

### Running a single test

```bash
cd server
/Users/issamzeinoun/claude/overcoding/.venv/bin/pytest tests/path/to/test_file.py::test_name -v
```

### Migrations

```bash
cd server
alembic revision --autogenerate -m "message"
alembic upgrade head
```

> **⚠️ STARTUP MIGRATIONS ARE CURRENTLY DISABLED.** `main.py:106-107` comments out `await asyncio.to_thread(_run_migrations)` with "TEMP WORKAROUND: Migrations are hanging." So the schema is **NOT** built in-process on boot right now — a fresh `opa.db` will have no tables until migrations run manually. Re-enabling this (and root-causing the hang) is Phase 2.1 in the action plan. `_run_migrations()` itself (runs `alembic upgrade head`) still exists at `main.py:27`.

**Every schema change needs a migration**: edit the model, then `alembic revision --autogenerate -m "…"`, review the diff. `alembic check` must report an empty diff before commit. See [`DATABASE.md`](./DATABASE.md) for the full runbook.

### Ports

Makefile uses **`:8001` / `:5174`** (README's `:8000`/`:5173` is stale). CORS in `app/main.py` covers those plus 5173/3000 and the sibling SPAs. Interactive docs: `http://localhost:8001/docs`.

## Architecture

OPA is a healthcare payment-integrity platform. FastAPI backend (`server/`), React + Vite + TS frontend (`client/`), SQLite via `aiosqlite` (`server/opa.db`). **~23 rule-based detectors** plus an AI/LLM analysis path run against claims; findings drive a case-management workflow (worklist → review → letter → recoupment) with an immutable audit log. Hosts both post-pay (PayGuard) and pre-pay (ClaimGuard) pipelines on one DB (`claims.pipeline_mode`).

### Backend layering

```
routes/      FastAPI routers — thin; pull session via Depends, call services
services/    Business logic — case creation, scoring, prioritization, disposition,
             audit, letters, reconciliation, ai_service (Claude), fwa, evidence
dao/         Async SQLAlchemy data access; one DAO per aggregate
detectors/   BaseDetector + ~23 concrete detectors + orchestrator
ml/          Training script + feature schema for the billing-variance classifier
models/      SQLAlchemy ORM split into reference, claims, workflow modules
schemas/     Pydantic v2 request/response
seed/        seed runner (seed_all.py)
```

### Detector pipeline

`detectors/orchestrator.py` instantiates **~23 detectors** (`grep -c "Detector()" orchestrator.py`) and runs them sequentially per claim. Each implements `BaseDetector.run(claim, db_session, enabled, score_multiplier) → List[DetectorResult]`. The orchestrator **swallows per-detector exceptions** (logs and continues) — a failing detector won't break the run but also won't surface loudly. **When debugging "missing findings," check logs for detector errors first.** (This masked the DET-20 typo bug — see Known bugs.)

`enabled_codes` and `score_multipliers` gate which detectors fire and rescale confidence — operator-tunable thresholds without code changes.

Representative detectors (NOT exhaustive — there are ~23; see `detectors/det_*.py`):

| Code   | File                          | Logic                                       |
|--------|-------------------------------|---------------------------------------------|
| DET-01 | det_01_duplicate.py           | Same member + CPT + service date            |
| DET-02 | det_02_retro_eligibility.py   | Member not enrolled at service date         |
| DET-04 | det_04_fee_schedule.py        | Paid > allowed × 1.05                       |
| DET-06 | det_06_ncci_mue.py            | NCCI mutually-exclusive pairs, MUE units    |
| DET-08 | det_08_excluded_provider.py   | OIG/SAM exclusion list match                |
| DET-09 | det_09_coding_errors.py       | Invalid ICD→CPT, unbundling patterns        |
| DET-18 | det_18_medical_necessity.py   | No covered Dx for CPT (LCD/NCD coverage)    |
| DET-20 | det_20_carveout_violation.py  | BH/pharmacy/DME carve-out violations (⚠ bug)|

`_DET_CODE_MAP` in `services/case_service.py` aliases legacy IDs (e.g. `DUPLICATE_CLAIM_V1` → `DET-01`) — both schemes appear in seeded data; always normalize through this map.

### AI / LLM path (ClaimGuard-style)

`services/ai_service.py` uses the **Anthropic SDK directly** (`import anthropic`; also used by `evidence_scanner_service.py`, `fwa_service.py`). Reads `ANTHROPIC_API_KEY` from env (load via `.env`). AI findings persist into the unified `findings` table with **`detector_id='CG-BASIC-V1'`** (constant `AI_DETECTOR_ID` at `ai_service.py:41`), `confidence`/`overpayment_amount` NULL (decided later in review). `ai_service._client`/`MODEL` is the single LLM config point, reused by `document_generation_service`.

> Note: older docs say `AI-CLAUDE-V1` — the code actually uses **`CG-BASIC-V1`**. (boto3/langfuse/penguin are still NOT present — only anthropic.)

### Scoring path (the real one)

1. **Provider ML score** — `app/ml/train_billing_variance.py` trains a classifier on behavioral features (`FEATURE_COLS`); each provider gets a `billing_variance_score`. Runs during `make seed`, overwrites the 0.5 seed. The forest is trained on SMOTE-balanced data, then **probability-calibrated** (Platt `sigmoid` / `isotonic`) on a natural-ratio holdout so the score reads as a true probability — `calibration_method` param (default `sigmoid`; carves a 60/20/20 core/calibration/validation split). The artifact stores both the calibrated scoring `model` and the raw `base_estimator` (SHAP / `feature_importances_` need the raw forest); `load_model()` vs `load_base_estimator()`.
2. **Case creation** — `services/case_creation_service.py:360` writes a `LikelihoodScore` with `composite_likelihood = provider.billing_variance_score` as the prior; the three sub-scores `cpt_risk_score`/`dx_cpt_mismatch_score`/`claim_complexity_score` are **hardcoded 0.0** (`case_creation_service.py:364-366`). `ScoringService.compute_claim_complexity()`/`compute_dx_cpt_mismatch()` exist but are not in the live path. (Old docs attribute this to `analyze.py` — it's `case_creation_service.py`.) **The prior (`composite_likelihood`) no longer feeds priority** — it's written/displayed and drives the model-vs-rules disagreement flag (`_is_model_rule_disagreement`: prior ≥ 0.70 and evidence ≤ leak + 0.02), but the ranking is evidence-driven (steps 4–5).
3. **Detectors run** → `Finding` rows.
4. **Evidence score** (`case_service._compute_evidence_score`; **Noisy-OR**, not the old sequential posterior) — combines fired findings' confidences: `E = 1 − (1 − L) × ∏(1 − f.confidence)` over non-informational findings, leak `L = RULE_LEAK = 0.03`.
   - DET-08 fires → `0.98` (hard override, bypasses the product)
   - No findings → `E = 0.03` (the leak floor — **not** `prior × 0.50`)
   - Informational ($0; `evidence.financial_impact is False`) findings are excluded so they can't inflate `E`
   - **The prior is not an input.** `_compute_posterior(prior, findings)` is now a back-compat alias that ignores `prior` and calls `_compute_evidence_score`; `posterior`/`posterior_score` on `CaseDetail` **is** the evidence score.
5. **Priority** (`scoring_service.compute_priority`, Option B / **EMV** — not the old additive `amount×0.60 + posterior×0.35`): `emv = evidence × amount_at_risk`, then `score = (min(emv / amount_cap, 1) × severity_weight + urgency × urgency_weight) × 100`. Amount and evidence are **multiplied**, so low confidence discounts big-dollar claims. Live defaults (`PrioritizationConfig`): `severity_weight=0.95`, `urgency_weight=0.05`, `amount_cap=5000`, `urgency_window_days=30` (no deadline → urgency `0.5`). Bands ≥75 HIGH / 50–74 MED / <50 LOW. `compute_priority_with_config` (real call site) reads these weights from the DB.

### Frontend

React 18 + Vite + TS + Tailwind + Recharts. Pages: `WorklistPage`, `CaseDetailPage`, `DashboardPage`, `LetterPage`, `AdminPage`, assistant panel. State via hooks; API calls in `services/`. No global store. Cross-app nav via `AppSwitcher`; API base URLs committed in `client/src/config/appUrls.ts` (not env). Several components (`AssistantPanel`, `DemoGate`, `ActorPicker`) are duplicated across the sibling SPAs — see `docs/codebase-map/cross-cutting/reuse-map.md` before editing them.

### Seed flow

`make seed` is **required** for a useful app — loads codes, providers, members, fee schedules, letter templates, trains ML, then creates demo cases by running real detectors against real seeded claims. Demo dates are relative to today; re-seed if stale.

### Persistence & auto-seed (demo mode — intentional)

> Full runbook: [`DATABASE.md`](./DATABASE.md).

Persistence is **intentionally ephemeral** — SQLite at a relative path (`config.py`), no Railway volume, every deploy starts empty. Schema is built by **Alembic migrations** (single squashed baseline under `migrations/versions/`, priors archived under `migrations/_archived_versions/`; `alembic check` clean). **BUT** the lifespan auto-run is currently disabled (see Migrations warning above) — to finish productionizing: re-enable startup migrations, attach a volume / move to Postgres, add a CI drift guard (`alembic upgrade head && alembic check`).

**Constraint naming + SQLite batch mode.** `Base.metadata` carries a `naming_convention` (`app/database.py`); `env.py` sets `render_as_batch=True`. Mandatory for SQLite (unnamed constraints can't be reflected). **Writing migrations:** `op.add_column` for plain adds (native ALTER, no rebuild); `batch_alter_table` only for drop/alter/constraint changes, with **named** constraints (explicit `name=` wins over the convention).

`_seed_if_empty()` runs the full seed only when `SEED_ON_EMPTY` is set AND `opa_users` is empty (idempotent). Off by default (local dev + tests never auto-seed); `railway.toml` sets `SEED_ON_EMPTY=1`. Seed runs in a worker thread, never crashes startup.

**`server_default` rule:** a SQL-level `DEFAULT` is emitted only for a column with `server_default=` — ORM-side `default=` alone does not. Any `NOT NULL` column a raw-SQL seed / X12 intake **omits** must carry `server_default=` on the model or the insert fails `NOT NULL constraint failed`. The baseline migration is autogenerated from models, so declare `server_default=` on the model and regenerate.

## Auth & identity

**No real per-user authentication.** `get_current_user` (`middleware/auth.py:33`) resolves identity in order: JWT bearer → API key → **`X-User-Id` header** → cookie → `system` fallback. The `X-User-Id` header is client-supplied and trusted — a **demo identity selector, not auth**. Anyone reaching the API can act as any user. **Do not expose the API publicly without a real gate.**

The legacy `DemoGateMiddleware` (`middleware/gate.py`) is **no longer the active path** — `main.py:125-126` notes it was "replaced by JWT Bearer token validation in get_current_user()." A login-token flow (`POST /api/auth/login`, HMAC, when `DEMO_PASSWORD` set) still exists for the shared-login wall; the frontend `DemoGate` + `opa_demo_token` localStorage drive it. RBAC is opt-in via `require_app(app)` / `require_role(role)` deps; frontends also gate UI with `NoAccessGate` on `user.apps[]`. **Real/sensitive data needs server-derived identity, not `X-User-Id` trust** (Phase 3 in the action plan). Note: the password check in `auth_service` is a placeholder (no bcrypt yet).

## ClaimGuard merger (pre-pay pipeline) — status

Schema unified to host PayGuard (post-pay) + ClaimGuard (pre-pay) on one DB. Discriminator `claims.pipeline_mode` = `'post_pay'` (default) | `'pre_pay'`. FWA is **not** a mode — it's a case/finding disposition from either pipeline. Multi-tenancy intentionally absent (one instance per payer).

- **Phase 1 (backend port) — DONE.** `ai_service.py`, `pdf_extraction_service.py`, `prepay_intake_service.py` (rejects unknown members/providers at intake → `IntakeValidationError`/422), prepay routes (`/api/prepay/claims/*`), documents + runtime-config routes. Deps: `anthropic`, `pdfplumber`, `fpdf2`. Uploads → `server/uploads/` (gitignored, `OPA_UPLOAD_DIR`).
- **Phase 2 (frontend re-point) — OUTSTANDING.** ClaimGuard SPA at `/Users/issamzeinoun/claude/claimguard/frontend` already targets OPA `:8001` but has open items (export modal bugs, UUID, comments→case_notes, etc.).
- **Phase 3 (delete old backend) — OUTSTANDING.**

> **Full per-item merger backlog: `docs/codebase-map/projects/claimguard.md` (MERGER_TODO).** Don't duplicate it here.

Pre-pay-aware columns: `claims.total_paid`/`paid_date`, `claim_lines.units_paid`/`paid_amount`/`allowed_amount` (all nullable); `claims.extracted_text`/`claim_summary`/`code_descriptions`; `claim_form_type`/`care_setting`/`drg`/`specialty`. `findings`: `detector_id`/`overpayment_amount`/`confidence`/`rule_version` nullable, `title`(≤200). Severity: PayGuard `low|medium|high`, ClaimGuard `critical|warning|ok` (unification deferred). `audit_logs` accepts `case_id` OR `claim_id`. `opa_users` extras: `initials`, `color_hex`, `specialty`, `supervisor_id`.

## Generic LLM document generation (shared)

Reusable: generate a finished doc from `{content, task_prompt, markdown_template}` → LLM fills the Markdown → rendered to PDF. **Distinct from PayGuard's deterministic letter flow** (`letter_service.py` + `letter_templates`, `{{placeholder}}` → HTML, untouched).
- **Table** `document_templates` (`models/workflow.py`), partitioned by `app` (`payguard`|`claimguard`); `version`/`is_active` carry `server_default`.
- **Service** `services/document_generation_service.py` — `generate(app, content, template_id=|template_markdown=, task_prompt=)`; reuses `ai_service._client`/`MODEL`; raises `DocumentGenerationError`/422.
- **PDF** `utils/markdown_pdf.py` (markdown→HTML→`fpdf2.write_html`; Railway-safe; swap to WeasyPrint if richer layout needed).
- **Routes** `routes/document_templates.py` (`/api/document-templates`): `GET ?app=`/`GET /{id}` (any), `POST`/`DELETE` (admin), `POST /generate` (streams PDF), `POST /generate-json` (preview).
- **Seed** `seed/seed_document_templates.py`, idempotent.

## DET-18 Medical Necessity — future accuracy (next phase)

DET-18 (`detectors/det_18_medical_necessity.py`) fires `NO_COVERED_DX_FOR_CPT` when a CPT has LCD/NCD coverage rules but no claim ICD satisfies them. Bounded by the `cpt_dx_coverage` seed catalogue (~30 rows, ~6 CPT families). **Option A** (do first): expand the catalogue (`seed/seed_codes.py` → `CPT_DX_COVERAGE`) — deterministic, zero runtime LLM cost. **Option B** (long tail): for CPTs with no coverage rows, ask Claude via `ai_service.py` whether the procedure is medically necessary given the Dx; return an AI finding (`CG-BASIC-V1`, NULL confidence), gated behind `ai_suggestions_enabled`. (Action plan Phase 5.5.)

## Known bugs (verified 2026-06-29) — see `docs/codebase-map/cross-cutting/risks-and-bugs.md`

- **DET-20 dead** — typo `BEHAVIORAL_HEALTH_CPts` (line 25) vs `self.BEHAVIORAL_HEALTH_CPTS` (line 82) → `AttributeError` on every HMO claim, swallowed by the orchestrator. One-char fix.
- **Startup migrations disabled** — `main.py:106-107` (see Migrations warning).
- **ClearLink MCP audit dropped** — object passed to positional `auditLog` (`clearlink/server/agents/agentLogger.js:72`).
- **claimguard export modals** — wrong path + no auth (frontend-only; backend `/api/prepay/claims/{id}/export/denial|approval` exists at `prepay_claims.py:1261/1300`).

## Notes when changing code

- **Per-line attribution for amount-at-risk.** `compute_at_risk_deduped` (`services/amount_at_risk.py`) attributes each claim line to its single highest-priority finding. New overlapping detectors must participate in this dedup via their `finding_type`.
- **Detector confidence ∈ [0,1].** Out-of-range silently distorts the posterior. Orchestrator clamps multiplied scores; the detector itself must emit valid confidences.
- **DET-08 is special-cased twice** — exclusion check AND posterior hard override. Change both sites.
- **Orchestrator swallows detector exceptions** — when adding a detector, test it in isolation; a silent `AttributeError` (like DET-20) produces zero findings with no error surfaced.
- **Class constant naming** — DET-20's bug was a case-typo on a class attribute; grep the attribute name before relying on it.
