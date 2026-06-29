# Data Models — shared entities & ownership

> OPA's SQLite (`server/opa.db`) is the canonical store for the whole suite (members, claims, users, cases, findings). ClearLink has its OWN SQLite (`clearlink/data/clearlink.db`) — a SEPARATE clinical store. The two member tables are NOT the same DB; they're synced/bridged only via the add-diagnosis seam.

## Ownership map

| Entity | Canonical owner | Also in | Notes |
|--------|-----------------|---------|-------|
| `members` | OPA `opa.db` | ClearLink `clearlink.db` (own copy) | OPA reference-data-first; ClearLink clinical copy. iam SPA edits OPA's via API. |
| `claims` / `claim_lines` | OPA | ClearLink `claims` (clinical window) | OPA `pipeline_mode` discriminator post_pay\|pre_pay |
| `findings` | OPA | — | detector findings vs AI findings (see below) |
| `opa_users` + RBAC | OPA | — | shared identity for ALL frontends (`apps[]`/`roles[]` gate UI access) |
| `opa_cases` | OPA | — | post-pay & pre-pay both create cases |
| `audit_logs` | OPA | ClearLink `audit_log` + `agent_tool_calls` | OPA accepts case_id OR claim_id |
| `siu_investigations` | OPA | — | FWA disposition, not a pipeline |
| `documents` | OPA | ClearLink `documents` | PDF uploads |
| connectors | OPA `connectors` | ClearLink `agent_tools` | both registry-style |

## OPA core tables (`server/app/models/`)

| Table | Key cols | Relationships / notes |
|-------|----------|-----------------------|
| `claims` | `pipeline_mode` (post_pay\|pre_pay), `total_paid`/`paid_date` (nullable=pre-pay), `extracted_text`, `claim_summary`, `code_descriptions` JSON, `claim_form_type`, `care_setting`, `drg` | hub entity |
| `claim_lines` | `units_paid`, `paid_amount`, `allowed_amount` (all nullable for pre-pay) | → claims |
| `findings` | `detector_id` (nullable), `overpayment_amount` (nullable), `confidence` [0,1] (nullable), `title`(≤200), `rationale`, `severity` | detector vs AI; **AI detector_id = `CG-BASIC-V1`** per code (CLAUDE.md says `AI-CLAUDE-V1` — DRIFT, verify) |
| `likelihood_scores` | `composite_likelihood`(=provider prior), `cpt_risk_score`/`dx_cpt_mismatch_score`/`claim_complexity_score` **hardcoded 0.0** | written at `case_creation_service.py:364-366` (NOT analyze.py per CLAUDE.md — DRIFT) |
| `providers` | `billing_variance_score` (ML output) | ML overwrites 0.5 seed at seed step 8 |
| `opa_users` | `apps[]`, `roles[]`, `initials`, `color_hex`, `specialty`, `supervisor_id` (self-FK) | identity for all frontends |
| `runtime_config` | flat k/v | feature flags (`ai_suggestions_enabled`, `high_dollar_threshold`, `auto_assign`) |
| `document_templates` | `app` (payguard\|claimguard), `task_prompt`, `template_markdown`, `version`, `is_active` | LLM doc-gen |
| `prioritization_config` / `ml_training_config` | singletons | formula weights |
| `audit_logs` | `case_id`\|`claim_id` (both nullable) | immutable audit |

## ClearLink core tables (`clearlink/server/db/`)

`members`, `diagnoses`, `icd_hcc_lookup`, `documents`, `claims`, **`agent_tools`** (connector registry: kind/sql_template/input_schema/mock/for_agents), **`agent_tool_calls`** (audit), `api_keys` (sha256), `agent_configs`, `agent_runs`/`agent_actions`, `nurse_alerts`, `compass_suggestions`, `audit_log`.

## Identifier normalization (canonical as of 2026-06-29)

Both the member business key and the claim human-readable number were renamed to consistent names across all three systems. Any session touching identifiers should use the names below — the old names are gone from the DB and server code.

### Member identifier

| | Old name | **Canonical name** | Example value |
|---|---|---|---|
| ClearLink `members` table | `member_id TEXT` | **`member_number TEXT`** | `"MA-000003"` |
| OPA `members` table | — | **`member_number`** (was already this name) | `"MA-000003"` |

**Cross-system join key:** `OPA.members.member_number = ClearLink.members.member_number`
This is the only reliable way to link a PayGuard/ClaimGuard claim to a ClearLink member record.

**ClearLink naming trap — do NOT confuse these two things:**
- `members.member_number TEXT` — the payer-assigned subscriber ID string (was renamed from `member_id`). This is the business key.
- `diagnoses.member_id`, `labs.member_id`, `claims.member_id`, `secure_messages.member_id`, etc. — these are **INTEGER FK columns pointing to `members.id`** (the internal auto-increment PK). They are correctly named `member_id` and were NOT touched in the rename.

### Claim identifier

| | Old name | **Canonical name** | Example value |
|---|---|---|---|
| ClearLink `claims` table | `claim_number TEXT` | **`icn TEXT`** | `"CLM-2026-00003"` |
| OPA `claims` table | — | **`icn`** (was already this name) | `"CLM-2026-00016"` |
| ClearLink CEE JSON blobs | `metadata.claim_number` | **`metadata.icn`** | — |

### OPA API — `member_number` is now in all claim responses

`PrepayClaimOut` / `PrepayClaimDetail` (OPA `server/app/schemas/prepay_schemas.py`) includes `member_number: Optional[str]`. It is populated in:
- `routes/prepay_claims.py` — both the list endpoint and the detail handler
- `services/ai_service.py` — the claim context dict fed to AI prompts

The ClaimGuard frontend (`src/api/types.ts` + `src/api/index.ts`) maps it through `adaptClaim` as `claim.member_number`.

### ID-type summary (all systems)

- OPA uses **UUID strings** for `user_id`, `claim_id`, `member_id` (internal PK).
- OPA `members.member_number` is a **string business key** (payer-assigned, human-readable).
- ClearLink uses INTEGER `id` as internal PK; `member_number` TEXT as business key.
- ClaimGuard frontend adapters `adaptClaim`/`adaptClaimDetail` in `src/api/index.ts` bridge OPA UUID ids to the UI shape.

### ⚠️ Master verification (2026-06-29): the rename is INCOMPLETE — 5 live breakages

Verified the identifier-normalization work above against the actual DB + code (this project holds the holistic/master view). **DB schema + the entire OPA side are correct:** ClearLink renamed `members.member_number` + `claims.icn`; OPA exposes `member_number` (`prepay_schemas.py:95`, `prepay_claims.py:312,620`). Stacy Truman join verified — OPA `123456` == ClearLink `123456`.

**However, the audit's claim that "the old names are gone from the DB AND server code" (line 40 above) is FALSE for ClearLink.** Five old-name references remain and will throw `no such column` — **3 of them on the LIVE MCP path the PayGuard assistant uses**, so the member-scoped ClearLink bridge is currently broken until fixed:

| # | Location | Broken reference | Fix | Impact |
|---|----------|------------------|-----|--------|
| 1 | `agent_tools.get_claims_window` (DB-resident SQL) | `SELECT … claim_number …` | `claim_number → icn` | assistant "claim history" tool errors |
| 2 | `agent_tools.get_member_demographics` (DB-resident SQL) | `m.member_id AS mrn` | `m.member_id → m.member_number` | assistant "eligibility"/member-360 errors |
| 3 | `clearlink/server/mcp/toolExecutor.js:86` | `SELECT id FROM members WHERE member_id = ?` | `member_id → member_number` | **breaks member resolution for EVERY member-scoped ClearLink MCP tool** (systemic) |
| 4 | `clearlink/server/utils/memberUtils.js:3` | `FROM members WHERE member_id = ?` | `member_id → member_number` | X12 member match breaks |
| 5 | `clearlink/server/db/seed.js:93` | `INSERT INTO members (… member_id …)` | `member_id → member_number` | re-seed only |

Why the audit missed #1–#2: they are **data inside `agent_tools.sql_template`, not source code** — a code-only grep/rename can't see them. #3 is the systemic one: `toolExecutor` resolves every inbound `member_id` to the internal PK through the now-missing column, so the whole member-scoped bridge is down.

**Correctly NOT touched:** FK columns named `member_id` on other tables (`diagnoses.member_id`, `claims.member_id`, `secure_messages.member_id`, …) point to `members.id` (INTEGER PK) — the audit's "naming trap" note is right about these.

> **Status: ✅ ALL 5 FIXED + verified (2026-06-29).** Connectors #1–#2 updated in `agent_tools.sql_template`; JS #3–#5 patched (`member_id`→`member_number`); ClearLink restarted. Verified by calling `executeMcpTool` for Stacy (123456): `get_member_demographics` returns `mrn:123456`, `list_diagnoses` returns her dx, `get_claims_window` returns `icn`, unknown member errors cleanly. See `CHANGELOG.md`.

## Finding taxonomy (two vocabularies — unification deferred)

| Field | PayGuard (post-pay) | ClaimGuard (pre-pay) |
|-------|---------------------|----------------------|
| `severity` | low\|medium\|high | critical\|warning\|ok |
| `detector_id` | DET-01..DET-20 etc. | `CG-BASIC-V1` (code) / `AI-CLAUDE-V1` (docs) |
| `confidence` | [0,1] float | NULL at gen time |
| `overpayment_amount` | set | NULL at gen time |

Column accepts either today; unification is an open decision.

## Pipeline discriminator (the central design choice)

`claims.pipeline_mode`: `'post_pay'` (PayGuard overpayment recovery) default, `'pre_pay'` (ClaimGuard claim review). FWA is NOT a pipeline mode — it's a case/finding disposition reachable from either. Multi-tenancy intentionally absent (one instance per payer).
