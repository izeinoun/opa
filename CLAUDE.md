# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All `make` targets are run from the repo root (`opa/`).

```bash
make setup     # pip install server reqs, npm install client, alembic upgrade head
make seed      # run server/seed/seed_all.py (13 steps; includes ML training)
make dev       # backend + frontend together; backend :8001, frontend :5174
make backend   # backend only (uvicorn --reload --port 8001)
make frontend  # frontend only (vite, :5174)
make verify    # python verify_env.py — checks ANTHROPIC/LANGFUSE/AWS env vars
make test      # cd server && pytest tests/ -v
make health    # curl :8001/health
make clean     # wipe opa.db, ml_models/, __pycache__
```

### Python environment

There is **no venv inside `opa/`**. The project uses a shared venv at the parent path: `/Users/issamzeinoun/claude/overcoding/.venv`. `uvicorn`, `pytest`, etc. are not on the system PATH — use that venv's `bin/` directly, or activate it before running raw commands. `make` targets call `uvicorn` unqualified and will fail unless the venv is active or the binary is on PATH.

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

The `lifespan` hook in `app/main.py` runs `alembic upgrade head` on startup (via `_run_migrations()`), so a missing DB is built from migrations automatically — in **every** environment. `create_all` is no longer used. **Every schema change needs a migration**: edit the model, then `alembic revision --autogenerate -m "…"` and review the diff (`alembic check` must report an empty diff before commit).

### Ports — README is wrong

The README documents `:8000` / `:5173`. The Makefile uses **`:8001` / `:5174`**, and CORS in `app/main.py` is configured for those plus 5173/3000. Trust the Makefile.

## README ≠ implementation — verified gaps

The README describes several things that are *not actually wired up*. Don't trust it for these without checking the code.

1. **Likelihood formula.** The README documents a 5-factor weighted sum (CPT × 0.30 + provider tier × 0.25 + Dx/CPT × 0.20 + complexity × 0.15 + ML variance × 0.10). The code does **not** compute this. In `routes/analyze.py` the `LikelihoodScore` row is created with `cpt_risk_score`, `dx_cpt_mismatch_score`, and `claim_complexity_score` hardcoded to `0.0`; `composite_likelihood` is just the provider's `billing_variance_score` (ML output) used as a prior. The actual likelihood used downstream comes from `_compute_posterior()` in `services/case_service.py` — a Bayesian update over detector findings (see Scoring below). `ScoringService.compute_claim_complexity()` and `compute_dx_cpt_mismatch()` exist but are not called in the live path.

2. **Priority weights.** README says amount 0.40 / likelihood 0.40 / urgency 0.20. Actual defaults in `services/scoring_service.py:17–19` are **0.60 / 0.35 / 0.05**.

3. **AWS Bedrock / Anthropic / Langfuse / Penguin SDK.** README's stack table lists all of these. The codebase contains only env-var holders in `app/config.py` and checks in `verify_env.py` — there are no `boto3`, `anthropic`, `langfuse`, or `penguin` imports anywhere under `server/app/`, no `invoke_model`/`messages.create` calls, and no LLM tracing. The string `LLM_DETECTORS = {"DET-09"}` in `disposition_service.py` is just a routing label; DET-09 itself is deterministic. Treat these integrations as planned, not present.

## Architecture

### High level

OPA is a healthcare payment-integrity auditing platform. FastAPI backend (`server/`), React + Vite + TS frontend (`client/`), SQLite via `aiosqlite` (`server/opa.db`). Six rule-based overpayment detectors run against claims; findings drive a case-management workflow (worklist → review → letter → recoupment) with an immutable audit log per case.

### Backend layering

```
routes/      FastAPI routers — thin; pull session via Depends, call services
services/    Business logic — case creation, scoring, prioritization, disposition,
             audit, letters, reconciliation
dao/         Async SQLAlchemy data access; one DAO per aggregate
detectors/   BaseDetector + 6 concrete detectors + orchestrator
ml/          Training script + feature schema for the billing-variance classifier
models/      SQLAlchemy ORM split into reference, claims, workflow modules
schemas/     Pydantic v2 request/response
seed/        13-step seed runner (seed_all.py)
```

### Detector pipeline

`detectors/orchestrator.py` instantiates the six detectors and runs them sequentially per claim. Each implements `BaseDetector.run(claim, db_session) → List[DetectorResult]`. The orchestrator **swallows per-detector exceptions** (logs and continues) — a failing detector won't break the run, but it also won't surface loudly. When debugging "missing findings," check logs for detector errors first.

`enabled_codes` and `score_multipliers` parameters let callers gate which detectors fire and rescale confidence; this is how operator-tunable thresholds work without code changes.

| Code   | File                          | Logic                                       |
|--------|-------------------------------|---------------------------------------------|
| DET-01 | det_01_duplicate.py           | Same member + CPT + service date            |
| DET-02 | det_02_retro_eligibility.py   | Member not enrolled at service date         |
| DET-04 | det_04_fee_schedule.py        | Paid > allowed × 1.05                       |
| DET-06 | det_06_ncci_mue.py            | NCCI mutually-exclusive pairs, MUE units    |
| DET-08 | det_08_excluded_provider.py   | OIG/SAM exclusion list match                |
| DET-09 | det_09_coding_errors.py       | Invalid ICD→CPT, unbundling patterns        |

`_DET_CODE_MAP` in `services/case_service.py` aliases legacy detector IDs (e.g. `DUPLICATE_CLAIM_V1` → `DET-01`) — both naming schemes appear in seeded data; always normalize through this map.

### Scoring path (the real one)

1. **Provider ML score** — `app/ml/train_billing_variance.py` trains a classifier on seven behavioral features (see `FEATURE_COLS`); each provider gets a `billing_variance_score`. This runs during `make seed` step 8 and overwrites the initial 0.5 seed.
2. **Case creation** (`routes/analyze.py`) writes a `LikelihoodScore` with `composite_likelihood = provider.billing_variance_score` as the prior.
3. **Detectors run** via the orchestrator and produce `Finding` rows.
4. **Posterior** (`case_service._compute_posterior`):
   - If DET-08 fires → `0.98` (hard rule, bypasses Bayesian update)
   - No findings → `prior × 0.50`
   - Else sequential update: `p ← p + (1 - p) × f.confidence` for each finding
5. **Priority** (`scoring_service.compute_priority`):
   `(amount_norm × 0.60 + posterior × 0.35 + urgency × 0.05) × 100`
   Bands: ≥75 HIGH, 50–74 MEDIUM, <50 LOW. Urgency ramps linearly from 0 at 30+ days out to 1 at deadline.

`compute_priority_with_config` (used by the real call site in `routes/analyze.py`) reads weights/thresholds from `priority_config` in the DB, so production weights may differ from the function defaults.

### Frontend

React 18 + Vite + TS + Tailwind + Recharts. Pages: `WorklistPage`, `CaseDetailPage`, `DashboardPage`, `LetterPage`, `AdminPage`. State via hooks; API calls in `services/`. No global store. Vite proxies API calls to `:8001`.

### Seed flow

`make seed` is **required** for the app to be useful — it loads codes, providers, members, fee schedules, letter templates, trains the ML model, then creates 15 demo cases by running real detectors against real seeded claims. Demo case dates are relative to today, so re-seed if the demo looks stale.

### Persistence & auto-seed (demo mode — intentional)

> **Full runbook:** see [`DATABASE.md`](./DATABASE.md) for the schema-build mechanisms, the create_all-vs-alembic collision, the `server_default` rule, Railway persistence validation, and the step-by-step production path. Summary below.

Persistence is **intentionally ephemeral**. The DB is SQLite at a relative path (`config.py`), with no Railway volume — every deploy starts from an empty filesystem. Schema is built by **Alembic migrations** in all environments: the lifespan hook (`main.py`) runs `alembic upgrade head` on startup. The chain has been **squashed to a single baseline** (`migrations/versions/…_baseline_squashed_schema.py`, the prior 16 revisions archived under `migrations/_archived_versions/`); models == migrations == DB is verified (`alembic check` is clean). To finish productionizing: attach a volume / move to Postgres so data survives deploys, and add a CI drift guard (`alembic upgrade head && alembic check`).

So each Railway deploy comes up empty. The lifespan hook calls `_seed_if_empty()`, which runs the full seed **only when `SEED_ON_EMPTY` is set AND `opa_users` is empty** (idempotent — warm restarts with data skip it). The flag is **off by default** so local dev and the test suite (both trigger the lifespan via `TestClient`) never auto-seed; `railway.toml` sets `SEED_ON_EMPTY=1` so deploys self-seed. The seed runs in a worker thread and never crashes startup on failure.

**`server_default` rule:** a SQL-level `DEFAULT` is only emitted for a column declared with `server_default=` — an ORM-side `default=` alone does **not** produce a DB default. So any `NOT NULL` column that a raw-SQL seed (or X12 intake) **omits** must carry `server_default=` in the model, or the insert fails with `NOT NULL constraint failed`. Because the baseline migration is autogenerated from the models, `server_default=` in the model now flows straight into the migration — so declare it on the model and regenerate. When adding a NOT NULL column, give it `server_default` if any raw INSERT might omit it.

## Auth & the demo gate

There is **no per-user authentication**: `get_current_user` (`middleware/auth.py`) trusts the client-supplied `X-User-Id` header (falling back to the `system` user), and the UI's user-switcher just sets it. This is a **demo identity selector, not auth** — anyone who can reach the API can act as any user. Do **not** expose the API publicly without a gate.

The **demo gate** (`middleware/gate.py`) provides a coarse shared-login wall for public deploys: when `DEMO_PASSWORD` is set, `DemoGateMiddleware` requires a signed token (from `POST /api/auth/login`) on every `/api/*` route except `/api/auth/*` and `/health`. Empty `DEMO_PASSWORD` (local dev, tests) disables it entirely. The `X-User-Id` persona switcher keeps working *behind* the gate. Tokens are stateless HMAC (`<exp>.<sig>`) signed with `SECRET_KEY`, 12h TTL. The assistant's in-process tool calls mint an internal token when the gate is on (`agent.py`); the frontend `DemoGate` shows a login screen and the api layer attaches the token + auto-logs-out on 401; the MCP server logs in via `OPA_PASSWORD`.

This gate is sufficient for a **synthetic-data demo**. Real/sensitive data or true multi-user access still requires proper token/SSO auth that derives identity server-side instead of trusting `X-User-Id`.

## ClaimGuard merger (pre-pay pipeline)

The schema has been unified to host both PayGuard (post-pay overpayment recovery) and ClaimGuard (pre-pay claim review) on a single database. The discriminator is `claims.pipeline_mode` — `'post_pay'` (default) or `'pre_pay'`. FWA is **not** a pipeline mode; it's a case/finding disposition that can arise from either pipeline.

Multi-tenancy is **not** in the schema by design — each payer deploys a separate instance.

Pre-pay-aware columns:
- `claims.total_paid`, `claims.paid_date` — nullable (pre-pay has no payment yet).
- `claim_lines.units_paid`, `paid_amount`, `allowed_amount` — nullable.
- `claims.extracted_text` (append-only AI evidence corpus), `claim_summary` (LLM-generated), `code_descriptions` (JSON `{code: desc}`) — ClaimGuard-style AI artifacts. PayGuard ignores them.
- `claims.claim_form_type` (CMS-1500 | UB-04), `care_setting` (Inpatient | Outpatient), `drg`, `specialty`, `description` — PDF/intake metadata.

AI-friendly `findings`:
- `detector_id`, `overpayment_amount`, `confidence`, `rule_version` — all nullable. AI findings use `detector_id='AI-CLAUDE-V1'` (or NULL), no confidence, no dollar amount at gen time. Determined later in review.
- `title` (max 200) added — ClaimGuard's short label. `rationale` is the body.
- Severity vocabulary: PayGuard uses `low|medium|high`; ClaimGuard uses `critical|warning|ok`. The column accepts either today; unification is a separate decision.

`audit_logs` accepts either `case_id` OR `claim_id` (both nullable). Pre-case lifecycle audits (PDF upload, initial AI analysis) populate `claim_id` only.

Two new tables:
- `documents` — PDF/file uploads attached to a claim and/or case. Replaces ClaimGuard's `documents`. Includes `uploaded_by_user_id` (improvement over ClaimGuard).
- `runtime_config` — flat key/value for operator feature flags (e.g. `ai_suggestions_enabled`, `high_dollar_threshold`, `auto_assign`). Distinct from the structured config singletons (`prioritization_config`, `detector_rule_config`, `ml_training_config`) which hold formula weights.

`opa_users` extensions for ClaimGuard's UI/routing: `initials`, `color_hex` (avatar tint), `specialty` (drives auto-assign), `supervisor_id` (self-FK).

## ClaimGuard merger — Phase 1 complete: backend port

ClaimGuard's backend functionality has been ported into this server. The unified backend now serves both post-pay (PayGuard) and pre-pay (ClaimGuard) pipelines on the same DB.

**Ported services**
- `services/ai_service.py` — Claude integration (analyze_claim / extract_claim_from_text / generate_claim_summary / generate_code_descriptions). Uses the Anthropic SDK directly; reads `ANTHROPIC_API_KEY` from environment (load via `.env`). AI findings persist into the unified `findings` table with `detector_id='AI-CLAUDE-V1'`, `confidence`/`overpayment_amount` NULL.
- `services/pdf_extraction_service.py` — thin pdfplumber wrapper.
- `services/prepay_intake_service.py` — converts an LLM-extracted claim dict into rows on `claims` + `claim_lines` + `documents`. **Rejects unknown members/providers at intake** (the "reference data first" rule). Raises `IntakeValidationError` → 422.

**Ported routes**
- `POST /api/prepay/claims/from-pdf` — upload, extract, validate, persist, optional auto-analyze
- `GET /api/prepay/claims` — list pre-pay claims (filtered by `pipeline_mode='pre_pay'`)
- `GET /api/prepay/claims/{id}` — detail; lazy auto-analyze on first visit when `ai_suggestions_enabled` flag is on
- `POST /api/prepay/claims/{id}/analyze` — re-run AI
- `POST /api/prepay/claims/{id}/recheck` — append recheck note + re-analyze
- `POST /api/prepay/claims/{id}/summary` — LLM summary
- `POST /api/prepay/claims/{id}/code-descriptions` — fill CPT/ICD short descriptions
- `POST|GET|DELETE /api/documents` + `/{id}/download` — file uploads at claim or case level
- `GET|PATCH /api/runtime-config` — flat key/value feature flags

**Environment**
- Requires `ANTHROPIC_API_KEY` in `opa/server/.env` (gitignored).
- New deps: `anthropic`, `pdfplumber`, `fpdf2`.
- Uploaded files land in `opa/server/uploads/` (gitignored). Configurable via `OPA_UPLOAD_DIR`.

## Generic LLM document generation (shared by both apps)

A reusable service generates a finished document from `{content, task_prompt, markdown_template}`: the LLM fills/expands the Markdown template using only the supplied content, and the result is rendered to PDF. Used by both PayGuard and ClaimGuard. **Distinct from PayGuard's deterministic letter flow** (`letter_service.py` + `letter_templates` + `provider_notices`), which does `{{placeholder}}` string substitution → HTML and is left untouched.

- **Table:** `document_templates` (in `models/workflow.py`) — one row per template, partitioned by the `app` discriminator (`'payguard'` | `'claimguard'`) so each app only sees its own. Columns: `task_prompt` (default LLM instructions), `template_markdown` (the body), `version`, `is_active`. `version`/`is_active` carry `server_default` per the fresh-DB raw-seed rule.
- **Service:** `services/document_generation_service.py` — `DocumentGenerationService.generate(app, content, template_id=|template_markdown=, task_prompt=)`. Resolves a stored template (scoped to `app`) or takes one inline; `task_prompt` can override the stored default. Reuses `ai_service._client`/`MODEL` (single LLM config point); raises `DocumentGenerationError` (→ 422).
- **PDF:** `utils/markdown_pdf.py` — `markdown` → HTML → `fpdf2.write_html` → PDF bytes. No system deps (Railway-safe); fpdf2's HTML/CSS support is intentionally basic. Swap this module's body for WeasyPrint if richer layout is ever needed — callers are insulated. New dep: `markdown`.
- **Routes:** `routes/document_templates.py`, prefix `/api/document-templates`. `GET ?app=` / `GET /{id}` (any app user); `POST` / `DELETE /{id}` (admin only); `POST /generate` (streams `application/pdf`); `POST /generate-json` (returns `{markdown, pdf_base64}` for preview).
- **Seed:** `seed/seed_document_templates.py` (step 7e in `seed_all.py`) — one starter template per app; idempotent.

## ClaimGuard frontend refactor (Phase 2 — not done yet)

For the next session, the ClaimGuard frontend at `/Users/issamzeinoun/claude/claimguard/frontend` needs:
- Re-point API base to OPA backend (`localhost:8001`).
- Switch to UUID strings for user_id and claim_id (was INTEGER).
- Adapt to new response shapes: `provider_name`/`patient_name` come back as strings derived from FKs (not the raw `provider`/`patient` strings); `cpts`/`icd10` come from `claim_lines` aggregation in the API response.
- `comments` flow → use `case_notes` (every reviewed claim gets a case first).
- Drop ClaimGuard's `/config` endpoint usage; use `/api/runtime-config` instead.
- Document upload calls move from `/claims/{id}/documents` to `/api/documents?claim_id=`.

## ClaimGuard backend retirement (Phase 3)

After frontend Phase 2 lands and the pre-pay UI fully runs against the unified backend, delete:
- `/Users/issamzeinoun/claude/claimguard/backend/` (entire directory)
- `/Users/issamzeinoun/claude/claimguard/backend/claimguard.db`

Anything in `claimguard/scripts/` or `claimguard/uploads/` that hasn't been ported should be audited first. Currently NOT ported (intentionally deferred): denial/approval ZIP export, evidence text search, provider message endpoint, X12 file ingest (PDF intake covers the main flow), form_pdf generators.

## Notes when changing code

- **Per-line attribution for amount-at-risk.** `compute_at_risk_deduped` in `services/amount_at_risk.py` attributes each claim line to its single highest-priority finding to avoid double-counting. If you add a new detector that overlaps with existing ones, make sure its `finding_type` participates in this dedup correctly.
- **Detector confidence is on [0,1].** Findings with confidence outside that range will silently distort the posterior. The orchestrator clamps multiplied scores but the detector itself must emit valid confidences.
- **DET-08 is special-cased twice.** It's both an exclusion check AND a hard override in posterior calculation. Changes to DET-08 semantics need to consider both call sites.
- **The README's interactive API docs link** (`/docs`) points to :8000; use `http://localhost:8001/docs`.
