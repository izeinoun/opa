# OPA — Overpayment Agent

Healthcare payment integrity auditing platform.

## Stack

| Layer     | Technology                                             |
|-----------|--------------------------------------------------------|
| Frontend  | React 18 + Vite + TypeScript + TailwindCSS + Recharts  |
| Backend   | Python 3.11 + FastAPI + SQLAlchemy 2.0 + aiosqlite     |
| Database  | SQLite (`server/opa.db`)                               |
| AI        | Penguin SDK → AWS Bedrock → claude-sonnet-4-6          |
| AutoML    | Penguin FDEAutoML (billing variance model)             |
| Tracing   | Langfuse                                               |

## Quick Start

```bash
# 1. Copy and configure env
cp server/.env.example server/.env
# edit server/.env with your keys

# 2. Install everything + run migrations
make setup

# 3. Seed the database (155 claims, 155 cases)
make seed

# 4. Start dev servers
make dev
# Backend:  http://localhost:8000
# Frontend: http://localhost:5173
# API docs: http://localhost:8000/docs
```

## Project Structure

```
opa/
├── client/          React frontend
│   └── src/
│       ├── pages/   WorklistPage, CaseDetailPage, DashboardPage, LetterPage, AdminPage
│       ├── components/
│       ├── hooks/
│       ├── services/
│       └── types/
└── server/          FastAPI backend
    ├── app/
    │   ├── models/     SQLAlchemy ORM (reference, claims, workflow)
    │   ├── schemas/    Pydantic v2 request/response schemas
    │   ├── dao/        Data access objects (async)
    │   ├── services/   Business logic
    │   ├── detectors/  6 overpayment detectors (DET-01,02,04,06,08,09)
    │   ├── ml/         AutoML billing variance classifier
    │   └── routes/     FastAPI routers
    └── seed/           Database seeders (13 steps)
```

## Detectors

| Code    | Name                     | Logic                                    |
|---------|--------------------------|------------------------------------------|
| DET-01  | Duplicate Billing        | Same member + CPT + service date         |
| DET-02  | Retro Eligibility        | Member not enrolled at service date      |
| DET-04  | Fee Schedule Variance    | Paid > allowed × 1.05                    |
| DET-06  | NCCI / MUE Violations    | Mutually exclusive CPTs, unit limits     |
| DET-08  | Excluded Provider        | Provider on exclusion list               |
| DET-09  | Coding / DX Errors       | Invalid ICD→CPT combos, unbundling       |

## Likelihood Formula

```
likelihood = cpt_risk_score × 0.30
           + (provider_risk_tier / 5) × 0.25
           + dx_cpt_mismatch_score × 0.20
           + claim_complexity_score × 0.15
           + billing_variance_score × 0.10
```

## Priority Score

```
priority_score = (amount_norm × 0.40 + likelihood × 0.40 + urgency × 0.20) × 100
```
Bands: ≥75 HIGH · 50–74 MEDIUM · <50 LOW · ≤5 days to deadline → force HIGH

## Useful Commands

```bash
make verify    # check env vars + connectivity
make test      # run pytest
make health    # curl /health
make clean     # wipe DB + cache
```

## API Reference

Interactive docs at `http://localhost:8000/docs` when server is running.

Key endpoints:

```
GET  /api/cases                       worklist with filters
GET  /api/cases/{id}                  case detail
POST /api/cases/{id}/transition       move case to next state
GET  /api/dashboard                   all dashboard metrics
GET  /api/letters/templates           letter templates
POST /api/letters/render              preview a letter
GET  /api/admin/reference-freshness   CMS/NCCI data freshness
```
