# Feature Guide — Administrator

**Audience:** platform administrators who configure the detection rules, scoring,
provider setup, users, templates, and reference data that drive the analyst and
supervisor experience.
**Scope:** the Admin area (PayGuard + ClaimGuard share one backend and rule set).

---

## 1. Administrator role

Admins tune *how* the platform behaves without code changes: which rules fire,
how cases are scored and prioritized, how providers are contacted, who can access
what, and what reference data the detectors run against. Most settings are live —
edits take effect on the next claim/case evaluation.

---

## 2. Detector Rules

**Admin → Detector Rules.** The single, shared rule catalog for both pipelines.

- **Enable/disable per pipeline:** each rule has an independent **Pre‑pay** and **Post‑pay** toggle. Greyed toggles mean the rule is structurally ineligible for that pipeline.
- **Weight:** a per‑rule confidence multiplier applied in the posterior update — raise/lower a rule's influence without disabling it.
- **Active vs. catalog:** "Active" rules are the implemented, enabled detectors; the full catalog also lists documented‑but‑unimplemented rules.
- Changes are audited and take effect immediately (the enabled‑rule set is cached and invalidated on save), so the analyst‑facing **"N fired / M run"** count and scoring reflect edits right away.

> The same detector engine runs for PayGuard and ClaimGuard; toggles are the only difference between the two pipelines, not separate code.

---

## 3. Prioritization

**Admin → Prioritization.** Controls the 0–100 **priority score** and its bands
(HIGH ≥75 / MED 50–74 / LOW <50).

- Adjust the weights blending **amount at risk**, **posterior likelihood**, and **urgency**.
- Live weights are read from configuration, so changes reshape every worklist immediately.

---

## 4. AI & runtime configuration

- **AI suggestions flag (`ai_suggestions_enabled`):** master switch for LLM features — per‑finding plain‑English explanations, ClaimGuard denial‑letter narrative paragraphs, and AI medical‑necessity suggestions. Off → the platform still runs fully deterministically.
- **High‑dollar threshold:** the dollar amount above which a terminal case decision is held for **supervisor approval**. Single source of truth, enforced consistently across the workflow.
- **Model tiers (env):** `ANTHROPIC_MODEL_SMART` (deep reasoning: audit, document generation) and `ANTHROPIC_MODEL_FAST` (low‑latency: assistant, finding explanations, denial summaries). Tune the cost/quality trade‑off per tier from configuration.
- **Rule Prompts:** edit the prompts used by AI‑assisted detectors.

---

## 5. Providers, fee schedules & delivery

**Admin → Providers / Provider Org detail.**

- **Fee schedules & contract limitations:** per provider org and line of business — the reference the mispricing/limitation detectors use.
- **Delivery playbook (email/portal):** set the provider's **contact email** (and delivery type). This is the address the **Send to Provider** and secure‑notice flows use, and an org becomes **"Active"** once it has a delivery email configured.
- **Provider Risk:** view provider behavioral risk scores (from the ML model) that seed case likelihood.

---

## 6. Users & access (RBAC)

**Admin → Users.**

- Create users; assign **roles** (analyst, supervisor, admin) and **apps** (PayGuard, ClaimGuard, SIU, …).
- App membership drives which workspaces and tabs a user sees; role drives capabilities (e.g. approvals are supervisor‑only).

> Note: the demo login is a placeholder check — harden authentication (bcrypt, real gate) before exposing to real credentials.

---

## 7. Templates

- **Letter Templates:** manage the `{{placeholder}}`‑based recoupment/notice letter templates per line of business (the deterministic PayGuard letter flow). Auto‑generation picks the active template for a case's LOB.
- **Document Templates:** manage the reusable Markdown templates used by the generic LLM document‑generation flow.

---

## 8. ML model management

**Admin → ML Model / Train Model.**

- The billing‑variance classifier scores each provider's behavior; that score seeds case likelihood.
- **Model tuning:** edit the training hyperparameters.
- **Train Model:** retrain and write updated provider scores + persist a model version. (Also runs during full seed.)

---

## 9. Reference data

**Admin → reference panels.** The lookup tables the detectors validate against:

- **CPT, ICD‑10, DRG, Modifier codes** — code validity and coverage checks.
- **Excluded Providers** — the OIG/SAM (LEIE) exclusion list DET‑08 screens rendering NPIs against.
- **Reference Freshness** — track how current each reference set is.
- CMS denial‑code (CARC) mapping backs the ClaimGuard denial letters.

---

## 10. Intake & documents

- **File Intake:** ingest claim files (incl. PDF extraction) and X12/835 remittance.
- **Unmatched Documents:** reconcile inbound documents that didn't auto‑attach to a claim/case.

---

## 11. Deployment & operations notes

- **Secrets (env, not committed):** `ANTHROPIC_API_KEY` (required for AI features), `JWT_SECRET_KEY`, `SECRET_KEY`, and optional `REQUIRE_AUTH=1` to close the API to logged‑in users only.
- **Non‑secret config** (URLs, CORS, model names, flags) lives in committed config, not dashboard variables.
- **Persistence:** the demo DB is intentionally ephemeral — each deploy migrates (`alembic upgrade head`) and, with `SEED_ON_EMPTY=1`, re‑seeds the demo dataset (users, providers, delivery playbooks, codes, cases). Attach a volume / Postgres before real data must survive deploys.
- **Deterministic first:** every core detection and scoring path runs without the LLM; AI features are additive and gated by `ai_suggestions_enabled`.

---

## 12. Admin surface at a glance

| Area | What you control |
|---|---|
| Detector Rules | Which rules fire (per pipeline) + their weights |
| Prioritization | Priority score weights & bands |
| Runtime config | AI on/off, high‑dollar threshold, model tiers |
| Providers | Fee schedules, contract limits, delivery email/portal |
| Users | Roles + app access (RBAC) |
| Templates | Letter & document templates |
| ML model | Training, hyperparameters, provider scores |
| Reference data | CPT/ICD/DRG/modifier codes, exclusions, freshness |
| Intake | File/835 intake, unmatched‑document reconciliation |
