# OPA — Overpayment Agent (HUB project)

Machine-readable context map. Paths relative to `/Users/issamzeinoun/claude/overcoding/opa`. Backend code under `server/app/`. VERIFY-flagged gaps noted inline.

---

## 1. IDENTITY

| Field | Value |
|---|---|
| Path | `/Users/issamzeinoun/claude/overcoding/opa` |
| Purpose | Healthcare payment-integrity auditing platform. Unified backend hosts PayGuard (post-pay overpayment recovery) + ClaimGuard (pre-pay claim review) + SIU (fraud) on one SQLite DB. |
| Backend stack | Python, FastAPI, SQLAlchemy 2.0 async + aiosqlite, Alembic, Pydantic v2 / pydantic-settings, Anthropic SDK, pdfplumber, fpdf2, scikit-learn/imbalanced-learn/shap (ML), paramiko (SFTP), `mcp` SDK |
| Frontend stack | React 18 + Vite + TS + Tailwind + Recharts (`client/`) |
| Backend entrypoint | `server/app/main.py` (`app = FastAPI(...)`, `uvicorn app.main:app`) |
| MCP entrypoints | mounted: `server/app/mcp_mount.py` at `/mcp`; standalone stdio: `server/mcp_server.py`; standalone HTTP: `server/mcp_remote.py` |
| Ports | backend **:8001**, frontend **:5174** (Makefile authoritative; README's :8000/:5173 is WRONG) |
| DB | SQLite `server/opa.db` (`sqlite+aiosqlite:///./opa.db`); ephemeral on Railway (no volume) |
| Python venv | shared at `/Users/issamzeinoun/claude/overcoding/.venv` (no venv inside `opa/`) |
| Run | `make setup` / `make seed` / `make dev` / `make backend` / `make frontend` / `make test` (`cd server && pytest tests/ -v`) / `make health` / `make clean` |
| File counts | `server/app/` ~158 .py; `client/src/` ~91 .tsx |

---

## 2. STRUCTURE

```
server/app/
  main.py            FastAPI app, lifespan, router mounting, SPA serve, exception handlers
  config.py          pydantic Settings (env), CORS origin lists, MCP_BEARER_TOKEN
  database.py        AsyncSessionLocal, get_db, Base + naming_convention
  mcp_mount.py       in-process MCP server mounted at /mcp (streamable-HTTP)
  mcp_format.py      MD_TOOLS set + format_markdown() for MCP tool output
  routes/            41 FastAPI routers (thin; Depends→services)
  services/          business logic (~38 modules)
  services/assistant/ Claude tool_use agent (agent.py, tools.py, prompt.py, clearlink_integration.py)
  dao/               async SQLAlchemy data access (one per aggregate)
  detectors/         BaseDetector + 23 detectors + orchestrator + helpers
  ml/                train_billing_variance.py, seed_training_data.py
  models/            ORM: reference.py, claims.py, workflow.py
  schemas/           Pydantic v2 request/response
  middleware/        auth.py (get_current_user/RBAC), gate.py (demo gate), error_handler.py
  utils/             markdown_pdf, letter_renderer, audit_builder, date_utils, scoring_utils
server/seed/         seed_all.py (multi-step) + per-aggregate seeders + ML train
server/migrations/   Alembic (single squashed baseline; archived under _archived_versions/)
server/mcp_server.py / mcp_remote.py   standalone MCP servers (stdio / HTTP)
client/src/
  pages/ (24)  components/ (admin,assistant,cases,charts,common,dashboard,layout,letters,workflow)
  services/ (api.ts + per-domain)  config/appUrls.ts  hooks/ lib/ types/ utils/
```

---

## 3. API ROUTES

All routers mounted in `server/app/main.py:143-195`. Each carries its own `/api` prefix. RBAC deps shown where present (`require_app`/`require_role`/`require_any_app` from `middleware/auth.py`).

### cases.py — prefix `/api/cases`, dep `require_app("payguard")`
| METHOD path | file:line | purpose |
|---|---|---|
| GET `` | cases.py:41 | worklist list (filters) |
| GET `/status-counts` | cases.py:76 | counts by status |
| GET `/{case_id}` | cases.py:103 | case detail |
| GET `/{case_id}/guidance` | cases.py:116 | case-guidance "what's next" |
| POST `/{case_id}/recoupment-letter` | cases.py:133 | generate recoupment letter PDF |
| POST `/bulk-assign` | cases.py:169 | bulk assign cases |
| POST `/{case_sequence}/adjudicate-without-claim` | cases.py:222 | decide an 835-only case |
| POST `/bulk-close` | cases.py:276 | bulk close |
| POST `/{case_id}/escalate/resolve` | cases.py:317 | resolve escalation |
| POST `/{case_id}/escalate` | cases.py:348 | escalate to supervisor |
| POST `/{case_id}/transition` | cases.py:396 | status transition |
| POST `/{case_id}/approve` | cases.py:416 | approve held decision |
| POST `/{case_id}/reject` | cases.py:437 | reject held decision |
| POST `/{case_id}/reopen` | cases.py:460 | reopen closed case |
| POST `/{case_id}/rerun-detectors` | cases.py:478 | re-run detectors |
| PATCH `/{case_id}/override-amount` | cases.py:504 | override overpayment amount |
| PATCH `/{case_id}/assign` | cases.py:543 | assign/take ownership |
| GET `/{case_id}/notices` | cases.py:599 | provider notices |
| GET/POST `/{case_id}/notes` | cases.py:640/662 | case notes |

### claims.py — prefix `/api/claims`
GET `` claims.py:13 (list); GET `/{claim_id}` claims.py:41 (detail).

### letters.py — prefix `/api/letters`, dep `require_app("payguard")`
GET `/templates` :26; GET `/templates/{id}` :35; PATCH `/templates/{id}` :53; POST `/render` :111; POST `/notices` :127; POST `/send` :138; GET `/notices/{case_id}` :150; POST `/cases/{case_id}/generate-notice` :158.

### dashboard.py — prefix `/api/dashboard`, dep `require_app("payguard")`
GET `` :203; `/summary` :217; `/kpis` :222; `/aging` :227; `/workload` :232; `/recovery` :237; `/detectors` :242; `/dx-coverage` :247; `/finding-acceptance` :282; `/rule-coverage` :333; `/briefing` :644 (daily briefing).

### dashboard_me.py — prefix `/api/dashboard`, dep `require_any_app(payguard,claimguard,fwa,cob)`
GET `/me` :209 (my performance dashboard); GET `/team` :218 (supervisor/admin team aggregate).

### admin.py — prefix `/api/admin`, dep `require_role("admin")` (32 routes)
Users: GET/PATCH `/users[/{id}]` :63/:70. Reference freshness: GET `/reference-freshness` :86, POST `/reference-freshness/{src}/refresh` :106. ML: GET `/model` :146, `/ml-models` :154, `/training-config` :159, PUT `/training-config` :164, POST `/model/retrain` :175, `/model/trial` :207, `/model/commit` :244. Code catalogs (CRUD): cpt-codes :295/:387, icd-codes :903/:414, drg-codes :658/:437, modifier-codes :689/:464, excluded-providers :349, cpt-dx-coverage GET/POST/DELETE :516/:536/:560, cpt-modifier-map GET/POST/DELETE :600/:621/:647. Prioritization config: GET/PUT :748/:754, affected-count :783, recompute :791. Detector rules: GET `/detector-rules` :856, PUT `/detector-rules/{rule_code}` :862.

### analyze.py — prefix `/api/analyze`, dep `require_app("payguard")`
POST `/835` analyze.py:29 → `case_creation_service.create_case_from_835` (post-pay case from X12 835).

### members.py — prefix `/api/members`, dep `require_any_app(payguard,claimguard)`
GET `` :77; GET `/{id}/360` :115 (cross-system member 360); POST `` :188; PUT `/{id}` :218; DELETE `/{id}` :250.

### ml.py — prefix `/api/ml`, dep `require_role("admin")`
GET `/info` :110; POST `/train` :115; POST `/upload` :127.

### fee_schedules.py — prefix `/api/fee-schedules`, dep `require_app("payguard")`
GET `` :62; GET `/{org_id}` :86; GET/PUT `/{org_id}/playbook` :140/:153 (provider delivery playbook).

### delivery.py — prefix `/api/cases`, per-route dep `require_app("payguard")`
GET `/delivery-queue` :15; POST `/{case_id}/send-notice` :31; PATCH `/{case_id}/delivery-result` :62.

### email.py — prefix `/api/email`
POST `/send` :21 (EmailJS transactional send; templates secure_link/otp/notify_payer).

### provider_messaging.py — prefix `/api/cases`, dep `require_app("payguard")`
POST `/{case_id}/send-notice-to-provider` :18; POST `/{case_id}/send-provider-inquiry` :45.

### findings.py — prefix `/api/findings`, dep `require_app("payguard")`
POST `/{finding_id}/accept` :91; `/reject` :119; `/adjust` :150 (FindingDisposition workflow).

### notifications.py — prefix `/api/notifications`, dep `require_any_app(payguard,claimguard,fwa,cob)`
GET `` :59; GET `/count` :88; POST `/{id}/read` :101; POST `/mark-all-read` :126.

### supervisor.py — prefix `/api/supervisor`, dep `require_role("supervisor","admin")`
GET `/approvals` :52; `/assignments` :152; `/escalations` :219.

### recoupments.py — prefix `/api/cases`, dep `require_app("payguard")`
POST `/{case_id}/recoupments` :60; GET `/{case_id}/recoupments` :146.

### contacts.py — prefix `/api/cases`, dep `require_app("payguard")`
GET/POST `/{case_id}/contacts` :55/:68 (ContactLog).

### provider_risk.py — prefix `/api/provider-risk`, dep `require_app("payguard")`
GET `` :178 (provider risk explanations from ML billing_variance).

### prepay_claims.py — prefix `/api/prepay/claims`, dep `require_app("claimguard")` (20 routes)
POST `/from-pdf` :422 (upload→extract→validate→persist→optional analyze); POST `` :526; GET `` :584; GET `/{id}` :657 (lazy auto-analyze); POST `/{id}/run-detectors` :682; `/recheck` :714; `/summary` :735; PATCH `/{id}/status` :761, `/case-status` :805; POST `/{id}/send-to-siu` :849; comments POST/GET :896/:931; POST `/{id}/code-descriptions` :954; PATCH `/{id}/assign` :1017; POST `/{id}/messages` :1059; GET `/{id}/evidence` :1081 (search AI corpus); PUT `/{id}/findings/{finding_id}/decision` :1112 (specialist accept/reject); POST `/{id}/findings-letter` :1223; GET `/{id}/export/denial` :1261, `/export/approval` :1300.

### prepay_dashboard.py — prefix `/api/prepay/dashboard`
GET `` :340; GET `/me` :363.

### prepay_evidence.py — prefix `/api/prepay/claims`, tag prepay-evidence
POST `/{id}/scan-evidence` :183; GET `/{id}/evidence-findings` :202.

### prepay_reports.py — prefix `/api/prepay/reports`, dep `require_app("claimguard")`
GET `/summary` :107; GET `/specialist/{user_id}` :177.

### evidence.py — prefix `/api/claims`, dep `require_any_app(payguard,claimguard,assistant)`
POST `/{claim_id}/validate-evidence` :64; GET `/{claim_id}/evidence-findings` :102.

### documents.py — prefix `/api/documents`, dep `require_any_app(payguard,claimguard,siu,assistant)`
GET `` :52; POST `` :104 (upload at claim/case level); GET `/{id}/download` :242; DELETE `/{id}` :273.

### runtime_config.py — prefix `/api/runtime-config`
GET `` :26; GET `/{key}` :32; PATCH `/{key}` :44 (dep `require_role("admin")`).

### rule_prompts.py — prefix `/api/rule-prompts`, dep `require_app("payguard")` (LLM rule prompts)
GET `` :115; `/active` :127; `/{id}` :136; POST `` :144; `/{id}/activate` :184; PUT `/{id}` :206; DELETE `/{id}` :232.

### users.py — 3 routers
`/api/users`: GET `` :62, POST `` :75 (admin), PATCH `/{id}` :114 (admin), GET `/{id}/roles` :139, POST/DELETE `/{id}/roles/{role_id}` :165/:188 (admin), GET `/{id}` :207. `/api/apps` (apps_router): GET :238, POST :253, PATCH `/{id}` :274. `/api/roles` (roles_router): GET :293, POST :299, PATCH `/{id}` :328, POST/DELETE `/{id}/apps/{app_id}` :344/:370.

### siu.py — prefix `/api/siu`, dep `require_app("siu")` (14 routes)
GET `/queue` :49; GET `/investigations/{id}` :64; GET (notes/cases) :111/:151; POST `/escalate` :188; POST/PATCH investigation lifecycle (notes, assign, status, LE referral, freeze) :199-:341.

### siu_dashboard.py — prefix `/api/siu/dashboard`, dep `require_app("siu")`
GET `` :366.

### connectors.py — prefix `/api/connectors` (admin)
GET `` :42; GET `/{id}` :57; POST `` :72; PATCH `/{id}` :106; DELETE `/{id}` :146; POST `/{id}/run` :165; `/{id}/test` :183; GET `/{id}/runs` :206.

### clearlink_proxy.py — prefix `/api/clearlink`
POST `/add-diagnosis` :94 → proxies to ClearLink MCP (`CLEARLINK_MCP_URL`).

### rules_evaluation.py — prefix `/api/cases`, dep `require_role("analyst","admin")`
POST `/{case_id}/reevaluate-rules` :33 (re-run rules after diagnosis change).

### document_templates.py — prefix `/api/document-templates`
GET `` :63; GET `/{id}` :75; POST `` :87 (admin); DELETE `/{id}` :108 (admin); POST `/generate` :138 (streams PDF); POST `/generate-json` :154.

### assistant.py — prefix `/api/assistant`
GET `/tools` :56; POST `/chat` :78; POST `/chat/stream` :95 (Claude tool_use agent loop).

### file_intake.py — prefix `/api/file-intake`, dep `require_role("admin","intake")`
POST `/upload` :406; GET `` :464; GET `/unmatched` :507; POST `/{id}/resolve` :522; GET `/{id}/download` :604; GET `/outputs` :633, `/outputs/{doc}/download` :653; DELETE `/{id}` :683.

### auth.py — prefix `/api/auth`
POST `/login` :51 (JWT issue); POST `/refresh` :73; GET `/me` :92; POST `/logout` :123.

### api_keys.py — prefix `/api/api-keys`
POST `/create` :36; GET `/list` :65; POST `/revoke/{id}` :85.

### secure_download.py — prefix `/api/secure-download`
GET `` :20 (HTML page); POST `/verify` :115 (OTP); GET `/file` :139.

### provider_portal.py — prefix `/api/provider-portal`
POST `/upload-recoup-notice` :35; GET `/upload-status/{case_id}` :166.

### Non-API
GET `/health` main.py:214; `/mcp` (MCP, 307 from bare path) main.py:206-211; SPA catch-all `/{full_path}` main.py:239.

---

## 4. DATA MODELS

Conventions: `*_id` PKs = `String(36)` UUID. "sd" = `server_default` (NOT NULL columns a raw seed/X12 insert may omit).

### Discriminators / pre-pay-aware columns
- **`claims.pipeline_mode`** sd `"post_pay"` — master `post_pay`|`pre_pay` switch (`models/claims.py:118`). `opa_cases.pipeline_mode` copied from claim.
- Nullable pre-pay columns on `claims`: `total_paid`, `paid_date`, `claim_form_type` (CMS-1500|UB-04), `care_setting`, `drg`, `extracted_text` (AI corpus), `claim_summary` (LLM), `code_descriptions` (JSON). On `claim_lines`: `units_paid`, `paid_amount`, `allowed_amount`, `service_date`, `revenue_code`, diag_1-4, modifier_1-4.
- `document_templates.app` / `intake_files.app` partition by `payguard`|`claimguard`.

### models/reference.py
| Table | line | key cols / relationships |
|---|---|---|
| provider_orgs | :21 | npi(uniq), tin, is_sensitive, risk_score; → providers, fee_schedules, playbook(1:1) |
| providers | :48 | FK provider_org_id; npi(uniq); specialty; is_excluded; **billing_variance_score (ML, default 0.5)** |
| excluded_providers | :74 | npi(idx); exclusion_type; sd source="OIG LEIE" — DET-08 source |
| members | :116 | member_number(uniq); coverage_effective/termination_date; retro_termination_date; date_of_death |
| cpt_codes | :133 | code(uniq); value_tier; risk_score; requires_auth; sd code_type/typical_setting/rule_certainty |
| icd_codes | :165 | code(uniq); chapter; valid_as_primary_dx; is_manifestation/etiology |
| drg_codes | :210 | code(uniq); weight; is_surgical; mcc_drg/base_drg |
| modifier_codes | :246 | code(uniq); payment_factor; ncci_override |
| cpt_modifier_map | :273 | composite PK (cpt_code, modifier_code) |
| cpt_dx_coverage | :292 | composite PK (cpt_code, icd_code); coverage_type required\|supporting\|excluded — DET-09/DET-18 source |
| fee_schedules | :313 | FK provider_org_id; cpt_code; **base_rate**; rate_basis — DET-04 source |
| contract_limitations | :335 | FK provider_org_id; limitation_type/value |
| reference_data_freshness | :355 | PK source_name; status fresh/stale/critical; affected_detectors(JSON) |
| evidence_requirements | :367 | code_type/code; required_evidence; severity_if_missing — AI evidence |
| bill_type_codes | :393 | code(uniq, UB-04) — DET-10 |
| revenue_codes | :410 | code(uniq, UB-04) — DET-10 |
| ml_model_versions | :427 | model_artifact_id; auc_roc; decision_threshold; feature_importance(JSON); is_active |
| cpt_coverage_gaps | :453 | PK cpt_code; needs_review — DET-18 populates |
| provider_delivery_playbooks | :474 | FK provider_org_id(uniq 1:1); delivery_type email\|portal; auth_config/navigation_steps(JSON) |

### models/claims.py
| Table | line | key cols |
|---|---|---|
| case_groups | :26 | group_number(uniq); FK provider_org/member; dos_range; duplicate_suspected |
| transactions_835 | :49 | transaction_number(uniq); total_amount; raw_835_json |
| era_adjustment_codes | :71 | FK payment_id; group_code(CAS); reason_code; amount |
| claim_payments_835 | :90 | FK transaction_id; claim_icn; **soft-FK claim_id/claim_line_id (nullable, 835→837 match)**; paid_amount |
| **claims** | :118 | PK claim_id; icn(uniq); FK member/provider_org/case_group(null)/era_transaction(null); **pipeline_mode** sd post_pay; claim_form_type/care_setting/drg(null); extracted_text/claim_summary/code_descriptions(null); total_billed; total_paid/paid_date(null); primary_icd; dx_pending sd 0 |
| claim_lines | :207 | FK claim_id; cpt_code; diag_1-4/modifier_1-4(null); units_billed; units_paid/paid_amount/allowed_amount(null) |

Helper `line_diag_codes(line)` claims.py:21.

### models/workflow.py
| Table | line | key cols |
|---|---|---|
| apps / roles / role_apps / user_roles | :21/:35/:48/:57 | RBAC: apps(payguard/claimguard/fwa/cob); composite PKs on role_apps/user_roles |
| **opa_users** | :71 | username(uniq); role(legacy); FK default_app_id; **initials**, **color_hex**, **specialty** (auto-assign), **supervisor_id (self-FK)**, is_active |
| api_keys | :100 | FK user_id; token_hash(uniq SHA256); expires_at; sd is_active=1 |
| **findings** | :116 | FK claim_id; claim_line_id(null); **detector_id (null; AI='CG-BASIC-V1'/'AI-EVIDENCE-V1'/NULL)**; **severity** (low/med/high OR critical/warning/ok); **confidence (null AI)**; **overpayment_amount (null AI)**; **title**≤200; rationale; issue_summary/suggestion(null AI); rule_version(null); status; fwa_indicator/fwa_rule_code |
| opa_cases | :159 | case_number(uniq); FK claim/case_group/provider_org/member/assigned_analyst(null); status; **pipeline_mode** sd post_pay; priority/priority_score; total_overpayment_amount(null); deadline_date/breached; FK siu_investigation_id(null); law_enforcement_hold/siu_frozen |
| case_notes | :255 | FK case_id; author_user_id; body |
| notifications | :271 | FK recipient/actor; kind; case_id(null); is_read |
| contact_logs | :310 | FK case_id; method/direction/summary |
| finding_dispositions | :327 | FK finding_id(uniq)/case_id; status accepted/rejected/needs_review/adjusted; original/adjusted_amount |
| prepay_finding_decisions | :362 | FK finding_id(uniq)/claim_id; status accepted/rejected |
| case_findings | :389 | composite PK (case_id, finding_id) |
| likelihood_scores | :402 | FK case_id(uniq); provider_risk_score; cpt_risk_score; dx_cpt_mismatch_score; claim_complexity_score; billing_variance_score; **composite_likelihood**; urgency_factor; priority_score |
| **audit_logs** | :426 | **FK case_id(null) OR claim_id(null)**; actor; action; from/to_state; meta_json; immutable |
| disputes | :456 | FK case_id; reason_code; status |
| letter_templates | :482 | **PK template_id (string e.g. INIT-NOTICE-MA)**; template_content; version |
| document_templates | :502 | **app** payguard\|claimguard; task_prompt; template_markdown; sd version=1/is_active=1 |
| provider_notices | :535 | FK case_id/template_id; letter_content; status; approved/sent |
| recoupment_actions | :564 | FK case_id; method; requested_amount; FK recovery_835_transaction_id(null) |
| detector_rule_config | :591 | **PK rule_code**; enabled_prepay/postpay; score; layer; applies_to; default_disposition |
| prioritization_config | :630 | **singleton PK 'current'**; amount_weight 0.60, likelihood_weight 0.35, urgency_weight 0.05, amount_cap 5000, urgency_window_days 30, high_threshold 75, medium_threshold 50 |
| ml_training_config | :648 | **singleton 'current'**; RF hyperparams; decision_threshold_mode auto_f2 |
| documents | :686 | FK claim_id/case_id/investigation_id/note_id(all null); filename; file_path; FK uploaded_by_user_id; extracted_text; extraction_status |
| intake_files | :731 | app; category 835/837/medical/claim_pdf; extracted_member/name/dob; candidate_case_ids(JSON); result_* FKs |
| code_evidence_requirements | :783 | code_type icd10\|drg; requirement_description |
| evidence_findings | :801 | FK claim_id/document_id(null)/requirement_id(null); result found/not_found/partial; evidence_text |
| runtime_config | :831 | **PK key (flat k/v)**; value; feature flags ai_suggestions_enabled, high_dollar_threshold, auto_assign |
| siu_investigations | :849 | investigation_type; status OPEN; outcome; escalation_source; law_enforcement_hold; siu_mode A\|B |
| investigation_cases | :899 | composite PK (investigation_id, case_id) |
| investigation_notes | :914 | FK investigation_id; is_confidential; immutable |
| law_enforcement_referrals | :937 | agency_name; referral_type/summary; outcome PURSUED/DECLINED(null) |
| connectors | :966 | name(uniq); kind http/sftp/internal/webhook; config/secret/input_schema_json; mock_enabled |
| connector_runs | :1011 | FK connector_id; correlation_id; ok; error_message; io_json |
| siu_export_packages | :1037 | FK investigation_id; version; integrity_hash(sha256); delivery_status |
| reconciliations | :1062 | FK case_id; expected/actual_amount; FK recovery_835_transaction/payment_id(null) |
| rule_prompts | :1094 | rule_id(idx); version; prompt_template; prompt_type evaluation/verification/explanation; sd model=claude-sonnet-4-6/temperature=0.0; UniqueConstraint(rule_id,prompt_type,version) |

---

## 5. DETECTORS

`detectors/base_detector.py`: `DetectorResult` dataclass (`detector_code`, `finding_type`, `description`, `overpayment_amount`, `confidence_score`, `evidence:dict`, `fwa_indicator`, `fwa_rule_code`) L6-19; `BaseDetector(ABC)` with class attrs `code`/`name`/`fwa_rule_code` and abstract `async run(claim, db_session) -> List[DetectorResult]` L30.

`detectors/orchestrator.py` `DetectorOrchestrator` (L30): instantiates **23 detectors** (L32-58) keyed by `d.code`. `run_all(claim, db, enabled_codes=None, score_multipliers=None)` L61: `enabled_codes` gates (skip if code not in set, L71); `score_multipliers` rescales each `confidence_score` clamped [0,1] (L84-88); stamps `fwa_rule_code`/`fwa_indicator` (L79-83); **per-detector try/except logs + continues — failures swallowed** (L90-95). `run_by_code` L98.

| Code | file | class:line | logic | finding_type |
|---|---|---|---|---|
| DET-01 | det_01_duplicate.py | :9 | same member+rendering NPI+service_from_date; full CPT overlap 0.95 / partial 0.75 | DUPLICATE_CLAIM (fwa FWA-06) |
| DET-02 | det_02_retro_eligibility.py | :8 | LOB mismatch 0.80; service before coverage_effective 0.95; after termination 0.95 | CROSS_LOB_MISMATCH / COVERAGE_NOT_YET_ACTIVE / COVERAGE_TERMINATED |
| DET-04 | det_04_fee_schedule.py | :16 | line paid > allowed×1.05; conf 0.85→0.45 if prior-auth/ClearLink approves | FEE_SCHEDULE_OVERPAYMENT |
| DET-06 | det_06_ncci_mue.py | :33 | NCCI mutually-exclusive CPT pairs 0.88→0.45; units > MUE 0.88 | NCCI_VIOLATION / MUE_EXCEEDED (fwa FWA-05) |
| DET-08 | det_08_excluded_provider.py | :9 | rendering NPI in LEIE/OIG-SAM or roster is_excluded; conf 1.0 | EXCLUDED_PROVIDER (fwa FWA-01) **— special-cased in posterior (0.98)** |
| DET-09 | det_09_coding_errors.py | :52 | excluded DX↔CPT (cpt_dx_coverage); unbundling; UB-04 inpatient CPTs (LLM) | DX_CPT_MISMATCH / UNBUNDLING / MULTIPLE_EM_SAME_DAY / CPT_ON_INPATIENT_UB04 |
| DET-10 | det_10_bill_type_revenue.py | :21 | institutional only: missing/invalid bill_type or revenue codes | MISSING_BILL_TYPE / INVALID_BILL_TYPE / INVALID_REVENUE_CODE |
| DET-13 | det_13_code_validity.py | :11 | CPT/ICD/modifier/pair/DRG not in reference or inactive for DOS | INVALID_CODE / INACTIVE_CODE / INVALID_MODIFIER / INVALID_CPT_MODIFIER_PAIR / INVALID_DRG |
| DET-16 | det_16_modifier_integrity.py | :18 | unknown modifier; mutually-exclusive; mod↔CPT prefix mismatch; mod-25 no procedure | UNKNOWN_MODIFIER / MUTUALLY_EXCLUSIVE_MODIFIERS / MODIFIER_CPT_TYPE_MISMATCH / MOD_25_WITHOUT_PROCEDURE |
| DET-18 | det_18_medical_necessity.py | :20 | CPT w/ LCD/NCD DX rules but no claim/doc/ClearLink ICD satisfies; uncatalogued→coverage gap + optional LLM | NO_COVERED_DX_FOR_CPT / NO_MEDICAL_NECESSITY / CODING_DEFICIENCY_NO_COVERED_DX |
| DET-19 | det_19_upcoding.py | :90 | **LLM-only**: high-level E/M codes w/ unsupporting DX; overpayment ≈ paid×0.30 | EM_UPCODING (fwa FWA-01) |
| DET-20 | det_20_carveout_violation.py | :16 | HMO carve-out (behavioral health OON / >20 visits no preauth; DME vendor) | CARVEOUT_* — **⚠️ BROKEN, see Known Issues** |
| FWA-02 | fwa_02_credential_mismatch.py | :88 | provider.specialty ≠ CptCode.specialty_typical for billed CPTs | credential_mismatch (fwa FWA-02) |
| FWA-03 | fwa_03_pos_mismatch.py | :80 | line pos_code not in expected set for CPT prefix | pos_mismatch (fwa FWA-03) |
| CHG-002 | chg_002_uniform_lines.py | :12 | ≥2 lines identical billed amount; 0.70 | UNIFORM_LINE_CHARGES |
| CHG-003 | chg_003_zero_dollar_line.py | :9 | any line billed_amount==0; 0.80 | ZERO_DOLLAR_LINE |
| STR-003 | str_003_revenue_code_on_professional.py | :11 | CMS-1500 carrying revenue codes; 0.92 | REVENUE_CODE_ON_PROFESSIONAL_CLAIM |
| STR-008 | str_008_missing_dos.py | :19 | service_from_date blank; 0.95 | MISSING_DOS |
| STR-009 | str_009_future_dos.py | :19 | service_from_date > today; 0.90 | FUTURE_DOS |
| STR-010 | str_010_missing_primary_dx.py | :17 | primary_icd blank; 0.95 | MISSING_PRIMARY_DX |
| STR-012 | str_012_charge_total.py | :14 | abs(total_billed − Σline) > 0.01; 0.95 | CHARGE_TOTAL_MISMATCH |
| STR-013 | str_013_missing_dob.py | :17 | submitted_patient_dob blank; 0.95 | MISSING_PATIENT_DOB |
| STR-014 | str_014_missing_member_id.py | :17 | submitted_member_number blank; 0.95 | MISSING_MEMBER_ID |

Helpers: `coverage_gap.py` `record_coverage_gap()` :26 (upserts CptCoverageGap, audit COVERAGE_GAP_DETECTED, returns MISSING_COVERAGE_RULE conf 0). `clearlink_detector_helper.py`: `search_clearlink_for_diagnoses` :22 / `_prior_auth` :68 / `_clinical_notes` :111 — wrap `call_clearlink_tool`, fail-safe. LLM-assisted FWA-04/FWA-07 live in `services/fwa_service.py` (called from analyze paths, not in orchestrator).

### Scoring / posterior path (the REAL one)
1. Provider ML `billing_variance_score` (`ml/train_billing_variance.py`, seed step) → written as prior.
2. **LikelihoodScore created in `services/case_creation_service.py:360-374`** (NOT `routes/analyze.py` — CLAUDE.md stale): `provider_risk_score`/`billing_variance_score`/`composite_likelihood` = `provider.billing_variance_score`; **`cpt_risk_score`/`dx_cpt_mismatch_score`/`claim_complexity_score` hardcoded 0.0**; urgency 0.5, priority 50.0 placeholders.
3. Detectors run (`services/detector_service.py`), produce Finding rows; detector_service:126-133 also overwrites `composite_likelihood` with rounded variance.
4. **`case_service._compute_posterior(prior, fired_findings)` L89-103**: DET-08 fires → **0.98**; no findings → **prior×0.50**; else sequential `p ← p + (1-p)×f.confidence`. `_DET_CODE_MAP` L148-161 normalizes legacy IDs (DUPLICATE_CLAIM_V1→DET-01 etc.).
5. Priority: `scoring_service.compute_priority` L11-53 default weights **0.60/0.35/0.05** (NOT README's 0.40/0.40/0.20), `(amount_norm×0.60 + posterior×0.35 + urgency×0.05)×100`; bands ≥75 HIGH / ≥50 MEDIUM / else LOW. Real call site `prioritization_service.compute_priority_with_config` L32-51 reads weights from `prioritization_config` singleton. `compute_claim_complexity`/`compute_dx_cpt_mismatch` exist but NOT called live.
6. Decision suggestion: `_suggest_decision` AUTO_RECOUP_CONF=0.90, AUTO_DROP_CONF=0.40; high-dollar gate `settings.high_dollar_threshold` (2000).

---

## 6. SERVICES

| Module | responsibility |
|---|---|
| ai_service.py | Anthropic Claude: analyze_claim, validate_evidence, extract_claim_from_text, extract_patient_identifiers, generate_claim_summary, generate_code_descriptions, run_rule_prompt. Single `_client()` + `MODEL=settings.llm_model`. AI findings detector_id='CG-BASIC-V1'/'AI-EVIDENCE-V1' |
| amount_at_risk.py | per-line de-duplicated amount-at-risk (`compute_at_risk_deduped`) |
| api_key_service.py | API key create/verify (SHA256 token_hash), list, revoke |
| audit_service.py | immutable audit_logs writes |
| auth_service.py | JWT create/verify (PyJWT, JWT_SECRET_KEY/HS256/1440min); `authenticate_user` (password check is placeholder — no bcrypt) |
| case_creation_service.py | create PayGuard post-pay case from X12 835; creates LikelihoodScore + runs detectors |
| case_guidance_service.py | workflow "where am I / what's next" engine |
| case_service.py | case CRUD, posterior compute, decision suggestion, serialization |
| claim_enrichment_service.py | enrich 835-created claim with dx + claim-form metadata |
| connector_service.py | execute connectors (http/sftp/internal/webhook); httpx + paramiko |
| delivery_service.py | provider notice delivery queue/result |
| detector_rule_service.py | upsert detector rule catalog metadata |
| detector_service.py | run detectors for a case, replace findings, update composite_likelihood |
| disposition_service.py | per-finding accept/reject/adjust; `LLM_DETECTORS={"DET-09"}` routing label |
| document_generation_service.py | generic LLM doc gen (app-scoped template → markdown → PDF) |
| edi_parser.py / edi_parser_837.py | X12 835 / 837 parsers |
| evidence_scanner_service.py | scan attached PDFs for medical-record support |
| export_service.py | denial/approval ZIP + X12 837 generation |
| fwa_service.py | LLM-assisted FWA detectors (FWA-04, FWA-07) |
| intake_matching_service.py | match inbound 837/medical-record doc to existing 835-based case |
| letter_service.py | deterministic recovery-notice generation ({{placeholder}}→HTML) |
| ml_model_service.py | ML model + training-config read/write |
| notification_service.py | notification emission helpers |
| pdf_extraction_service.py | pdfplumber text extraction |
| prepay_intake_service.py | pre-pay claim intake orchestrator; rejects unknown members/providers (IntakeValidationError→422) |
| prioritization_service.py | `compute_priority_with_config`, `recompute_open_cases` |
| provider_portal_service.py | provider portal recoup-notice upload automation |
| rbac_service.py | compute roles + app access for a user |
| reconciliation_service.py | recovery 835 reconciliation |
| recoupment_letter_service.py | provider recoupment letter PDF |
| reevaluation_service.py | re-run case evaluation after new evidence attached |
| rule_prompt_cache.py | in-memory cache of active rule prompts |
| scoring_service.py | `compute_priority` (defaults 0.60/0.35/0.05), unused complexity/mismatch helpers |
| siu_service.py | SIU escalation/investigation lifecycle, LE referrals, export packages |
| assistant/agent.py | Claude tool_use agent loop (Anthropic), write-action confirmation, ClearLink tool injection |
| assistant/tools.py | TOOLS registry (25 read/UI tools), WRITE_ACTIONS map, tools_for_apps RBAC scoping |
| assistant/clearlink_integration.py | fetch/call ClearLink MCP tools (httpx) |

---

## 7. EXTERNAL INTEGRATIONS

### Outbound
| Target | file:line | env / base URL |
|---|---|---|
| Anthropic Claude (messages.create) | ai_service.py `_client()` :355-363; agent.py | `ANTHROPIC_API_KEY` (os.getenv + .env); model `settings.llm_model` (LLM_MODEL/CLAIMGUARD_MODEL, default claude-sonnet-4-6), assistant `ASSISTANT_MODEL` (default claude-haiku-4-5-20251001) |
| ClearLink MCP (diagnosis proxy) | clearlink_proxy.py :48-60,:141 | `CLEARLINK_MCP_URL` (default http://localhost:8010), `CLEARLINK_API_KEY` |
| ClearLink MCP (assistant tools) | services/assistant/clearlink_integration.py :21-22 | `CLEARLINK_MCP_URL` (default http://localhost:8010/mcp), `CLEARLINK_MCP_API_KEY` (X-API-Key) |
| EmailJS (transactional) | routes/email.py; services + config | `EMAILJS_SERVICE_ID/PUBLIC_KEY/PRIVATE_KEY/TEMPLATE_ID_*` |
| Connector targets (http/sftp) | services/connector_service.py :116,:176 | per-connector config_json/secret_json (httpx, paramiko) |

> CLAUDE.md gap #3 (no anthropic/boto3) is now PARTIALLY STALE: `anthropic` IS a dependency (requirements.txt) and IS used (ai_service.py, agent.py). boto3/langfuse/penguin remain absent (only env holders in config.py).

### Inbound (who consumes OPA)
- Sibling frontends (PayGuard/ClaimGuard/SIU/IAM/Assistant/Intake) via CORS — origins baked into `config.py:84-125`.
- ClearLink — receives OPA-proxied add-diagnosis calls; OPA also consumes ClearLink MCP (bidirectional).
- MCP clients: Claude Desktop/Cowork (stdio `mcp_server.py`, HTTP `/mcp` mount, standalone `mcp_remote.py`).
- External portal agent / scripts via API keys (`/api/api-keys`).

---

## 8. MCP

Two surfaces. **Mounted in-process** (`app/mcp_mount.py`, `Server("opa-tools")`, `StreamableHTTPSessionManager(stateless=True)`) at `/mcp` on the main service (main.py:206-211). Lifespan runs `session_manager.run()` (main.py:114). Each tool maps to one OPA READ endpoint, executed in-process via `httpx.ASGITransport` (no self-HTTP); identity = `OPA_USERNAME` env → first admin; mints internal gate token when gate on. Tool list generated from `services/assistant/tools.TOOLS`; structured tools (`MD_TOOLS={get_case,search_cases,search_members}`, mcp_format.py:16) rendered to Markdown. Optional `MCP_BEARER_TOKEN` guard (default empty/open — config.py:157).

**Standalone stdio** `server/mcp_server.py` (`FastMCP("opa-assistant")`) — thin HTTP client, tools: `ask_opa` :153 (→ POST /api/assistant/chat agent loop), `send_email` :173 (→ /api/email/send), `search_claimguard_claims` :229 (→ /api/prepay/claims), `get_member_360` :251 (→ /api/members/{id}/360). Env `OPA_BASE_URL`, `OPA_PASSWORD`, `OPA_USER_ID`/`OPA_USERNAME`.

**Granular MCP tools exposed** (from `tools.py` TOOLS, backed by READ routes; method/path shown):
| tool | backing route | tools.py:line | apps |
|---|---|---|---|
| search_cases | GET /api/cases | :207 | payguard |
| get_case | GET /api/cases/{case_id} | :241 | payguard |
| get_case_guidance | GET /api/cases/{id}/guidance | :262 | payguard |
| get_case_notes | GET /api/cases/{id}/notes | :283 | payguard |
| get_payguard_dashboard | GET /api/dashboard | :303 | payguard |
| get_daily_briefing | GET /api/dashboard/briefing | :315 | payguard |
| list_provider_risk | GET /api/provider-risk | :341 | payguard |
| list_prepay_claims | GET /api/prepay/claims | :354 | claimguard |
| get_prepay_claim | GET /api/prepay/claims/{id} | :375 | claimguard |
| get_prepay_dashboard | GET /api/prepay/dashboard | :395 | claimguard |
| get_siu_dashboard | GET /api/siu/dashboard | :407 | siu |
| search_members | GET /api/members | :420 | () any |
| get_my_dashboard | GET /api/dashboard/me | :443 | () |
| get_member_360 | GET /api/members/{id}/360 | :467 | () |
| send_notice_to_provider | POST /api/cases/{id}/send-notice-to-provider | :492 | payguard |
| send_provider_inquiry | POST /api/cases/{id}/send-provider-inquiry | :514 | payguard |
| list_medications/list_diagnoses/list_dates_of_service/get_claims_window/get_labs_window/list_prior_authorizations/get_member_demographics | GET /mcp/proxy/tools/* (ClearLink) | :544-:691 | () |

UI/control tools (no route): `ask_user` :41, `present_view` :73, `confirm_action` :155 (only path to WRITE — enum from `WRITE_ACTIONS` :139-151: take_ownership, assign_case, transition_case, approve_case, reject_case, escalate_to_supervisor, accept_finding, reject_finding, adjust_finding, generate_provider_notice, reevaluate_rules). `TOOLS_BY_NAME` :705, `tools_for_apps()` :708 scopes by user apps.

---

## 9. AUTH & GATES

- **`get_current_user`** (`middleware/auth.py:33`): resolves user from (1) `Authorization: Bearer` → JWT (`AuthService.verify_token`) or API key (`APIKeyService.verify_api_key`); (2) `X-User-Id` header (internal/agent calls); (3) `opa_token` httpOnly cookie. Falls back to `system` user if none. Trusts X-User-Id — **demo identity selector, not real auth**.
- **JWT**: `services/auth_service.py` (PyJWT, `JWT_SECRET_KEY`/HS256/`JWT_EXPIRY_MINUTES`=1440). `authenticate_user` password check is a placeholder (no bcrypt/password_hash).
- **RBAC** (opt-in): `require_app(name)` :96, `require_any_app(*names)`, `require_role(*roles)` consult user_roles+role_apps via `RBACService`. Legacy `get_current_user_role` (X-User-Role header), `require_supervisor`/`require_admin`.
- **Demo gate** (`middleware/gate.py`): `DemoGateMiddleware` requires HMAC token (`make_token`/`verify_token`, SECRET_KEY, 12h TTL) on `/api/*` except `_OPEN_PATHS={/api/auth/login,/api/auth/status,/health}` when `DEMO_PASSWORD` set. **⚠️ NOT currently added to the app** — main.py:125-126 comment says "DemoGateMiddleware replaced by JWT". Gate code still used by MCP mount (`gate_enabled`/`make_token`) and agent write-exec for internal tokens.
- **API keys**: `services/api_key_service.py` (SHA256 hash, `generate_token`, verify with expiry).
- **Cross-app SSO**: `opa_token` cookie; CORS `allow_credentials=True`; see CROSS_APP_SSO_COMPLETE.md.

---

## 10. CONFIG & ENV

`config.py` Settings (env via `.env`, `extra=ignore`):
| env | default | purpose |
|---|---|---|
| DATABASE_URL | sqlite+aiosqlite:///./opa.db | DB |
| ANTHROPIC_API_KEY | "" | Claude (also read via os.getenv in ai_service) |
| LLM_MODEL (alias CLAIMGUARD_MODEL) | claude-sonnet-4-6 | main reasoning model |
| ASSISTANT_MODEL | claude-haiku-4-5-20251001 | in-app assistant |
| HIGH_DOLLAR_THRESHOLD | 2000.0 | supervisor approval gate |
| SECRET_KEY | dev-secret-key… | demo-gate token signing |
| JWT_SECRET_KEY / JWT_ALGORITHM / JWT_EXPIRY_MINUTES | …/HS256/1440 | JWT |
| DEMO_PASSWORD | "" | enables demo gate (empty=disabled) |
| SEED_ON_EMPTY | False | seed on empty DB at startup (Railway sets =1) |
| ENVIRONMENT | development | env label (banner) |
| ML_MODELS_DIR | ./ml_models | trained model artifacts |
| CORS_ALLOW_ORIGINS | "" | extra origins (dev+prod baked into _DEV/_PROD_CORS_ORIGINS) |
| EMAILJS_SERVICE_ID/PUBLIC_KEY/PRIVATE_KEY/TEMPLATE_ID_SECURE_LINK/OTP/NOTIFY_PAYER | "" | EmailJS |
| AWS_PROFILE/AWS_REGION/LANGFUSE_* | holders only | NOT wired (no boto3/langfuse imports) |
| MCP_BEARER_TOKEN | "" (config.py:157) | optional /mcp guard |
| CLEARLINK_MCP_URL / CLEARLINK_API_KEY / CLEARLINK_MCP_API_KEY | localhost:8010 | ClearLink (os.getenv, not in Settings) |
| OPA_USERNAME/OPA_USER_ID/OPA_PASSWORD/OPA_BASE_URL/OPA_TIMEOUT | — | MCP server identity (os.getenv) |
| OPA_UPLOAD_DIR | server/uploads/ | upload dir |

Config singletons/tables: `prioritization_config` & `ml_training_config` (PK 'current'); `detector_rule_config` (per rule_code); `runtime_config` (flat k/v feature flags: `ai_suggestions_enabled`, `high_dollar_threshold`, `auto_assign`); `rule_prompts` (LLM prompt versions).

---

## 11. FRONTEND

`client/` React 18 + Vite + TS + Tailwind + Recharts. Vite dev port **5174**, proxies `/api`→`http://localhost:8001` (`vite.config.ts`). API base `/api` (`services/api.ts:7`, axios instance with X-User-Id/token interceptors).

- **Cross-app URLs**: `src/config/appUrls.ts` — committed DEV/PROD maps (NOT env vars); `import.meta.env.PROD` selects. `API_BASE_URL`, `APP_URLS` {iam, payguard, claimguard, siu, assistant}, `appUrl(app, path)` deep-link helper. PROD hosts `*.penguinai.studio`.
- **Pages (24)**: WorklistPage, CaseDetailPage, DashboardPage, AnalystDashboardPage, LetterPage, AdminPage, ApprovalsPage, AssignmentsPage, EscalationsPage, ClosedCasesPage, DeliveryQueuePage, MembersPage, ProvidersPage, ProviderOrgDetailPage, ProviderRiskPage, FeeSchedulesPage, TeamPerformancePage, TrainModelPage, FileIntakePage, UnmatchedDocumentsPage, OutputFilesPage, Analyze835Page, LoginPage, SecureDownloadPage.
- **Components**: common/ (AppSwitcher cross-app nav using APP_URLS, SideNav, TopBar, DemoGate login wall, NoAccessGate RBAC, NotificationBell, EnvironmentBanner, PriorityBadge, StatusBadge, DataTable), plus admin/assistant/cases/charts/dashboard/layout/letters/workflow.
- **Services**: api.ts, authService, caseService, dashboardService, evidenceService, fileIntake, fileView, letterService, recoupmentService.
- **State**: hooks only, no global store.

---

## 12. KNOWN ISSUES / GAPS / TODOs

**README/CLAUDE ≠ impl (verified):**
1. Likelihood 5-factor weighted sum — NOT computed. `cpt_risk_score`/`dx_cpt_mismatch_score`/`claim_complexity_score` hardcoded **0.0** in `case_creation_service.py:364-366` (CLAUDE.md says routes/analyze.py — **also stale**: analyze.py is now a thin delegator). Real likelihood = `_compute_posterior` (case_service.py:89).
2. Priority weights — actual **0.60/0.35/0.05** (scoring_service.py:17-19 / prioritization_config singleton), NOT README's 0.40/0.40/0.20.
3. CLAUDE.md "no anthropic" — **STALE**: anthropic IS a dep and used (ai_service.py, agent.py). boto3/langfuse/penguin still absent.
4. CLAUDE.md detector table lists 6 detectors; orchestrator runs **23** (+ LLM FWA-04/07 in fwa_service.py).
5. AI finding detector_id — CLAUDE.md says `AI-CLAUDE-V1`; code uses `CG-BASIC-V1` (ai_service.py:41) and `AI-EVIDENCE-V1` (:45).

**Active bugs / risky state:**
6. **Migrations DISABLED**: `main.py:106-108` comments out `_run_migrations()` ("TEMP WORKAROUND: Migrations are hanging") — schema NOT built from Alembic at startup despite CLAUDE.md/railway.toml claims. (railway.toml startCommand still runs `alembic upgrade head` externally.)
7. **DET-20 broken/dead**: `det_20_carveout_violation.py` — misspelled attr `BEHAVIORAL_HEALTH_CPts` (:25) → AttributeError; constructs `DetectorResult` with nonexistent kwargs (detector_id/title/rationale/confidence/claim_line_id) → TypeError; non-conforming run() signature. Raises every run, silently swallowed by orchestrator → never emits findings.
8. **DemoGateMiddleware not registered** (main.py:125) — gate replaced by JWT but `_OPEN_PATHS`/gate code still referenced by MCP mount + agent; partial migration.
9. Orchestrator swallows all per-detector exceptions (orchestrator.py:90) — failing detectors silent; check logs for "Detector X failed".
10. `auth_service.authenticate_user` password check is a placeholder (no bcrypt) — note at auth_service.py:51.

**Half-done merges (ClaimGuard):**
11. Phase 1 (backend port) DONE. Phase 2 (separate ClaimGuard frontend repoint to :8001 / UUID ids / response shapes) NOT done. Phase 3 (delete claimguard/backend) pending Phase 2.
12. Persistence intentionally ephemeral (SQLite, no Railway volume); `SEED_ON_EMPTY=1` self-seeds each deploy. TODO: Postgres/volume + CI drift guard (`alembic upgrade head && alembic check`).
13. DET-18 accuracy bounded by `cpt_dx_coverage` catalogue (~30 rows); Option A (expand seed) + Option B (LLM fallback gated on `ai_suggestions_enabled`) planned.
14. ~70 root-level *.md/*.txt design docs + scratch files (FOUR_LAYER_PATTERN_*, PAYGUARD_CLAIMGUARD_COMPATIBILITY.md, migrate_*.py) — design intent, may drift from code.
