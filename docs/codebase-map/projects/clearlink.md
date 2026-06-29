# clearlink — codebase map (machine-readable)

Profiled commit context: branch main. Verified against code on 2026-06-29. `path:line` refs are relative to `/Users/issamzeinoun/claude/clearlink`.

## 1. IDENTITY
- **Path:** `/Users/issamzeinoun/claude/clearlink`
- **Purpose:** Healthcare member-care / payer platform (PCMH risk + CMS-HCC RAF scoring, clinical extraction from PDFs, prior-auth, claims, multi-agent automation). Owns the **canonical LLM fuzzy member search** and the **reference MCP tool server** consumed by OPA.
- **Stack:** Node.js (ESM, `"type":"module"`), Express 4.18, better-sqlite3 12.9 (synchronous SQLite), axios 1.6, `@anthropic-ai/sdk` ^0.106, jsonwebtoken 9, bcryptjs, express-fileupload, pdfjs-dist 3.11, uuid, node-cron, dotenv, cors. Frontend: React/TS + Vite + Tailwind (`client/`).
- **Node version:** not pinned in package.json (no `engines`); `nixpacks.toml` drives Railway build.
- **Entrypoint(s):** server `server/index.js` (`npm run server` = `node server/index.js`); client `client/` Vite dev.
- **Port:** `PORT` env; `.env.example` default `3000`, **actual `.env` = 8010** (`server/index.js:45`). OPA expects clearlink at `http://localhost:8010`.
- **Scripts (`package.json`):** `dev`(concurrently server+client), `server`, `client`, `build`(client), `migrate`(`server/db/migrate.js`), `seed`(`server/db/seed.js`), `setup`(migrate+seed), `start`(setup + node server/index.js).
- **DB file:** `DB_PATH` env, default `./data/clearlink.db` (`server/db/database.js:8`); WAL mode, `foreign_keys=ON`. Repo also has stale `clearlink.db` at root (used by sqlite3 inspection here).

## 2. STRUCTURE
```
server/
  index.js              Express app bootstrap, route mounting, CORS, scheduler init
  middleware/           authMiddleware(JWT), apiKeyMiddleware(sha256 api_keys), errorMiddleware
  routes/               ~30 Express routers (REST + MCP REST conveniences)
  controllers/          request handlers for members/auth/chat/messages/provider/sms/extraction
  services/             pdf, claude, x12(837/835/278), sms, voice, email, otp, token, extractionPipeline, insights, document, activity, message
  agents/               9 named agents + framework: charlie(tool-loop), dynamicAgent, scheduler, agentLogger, agentRegistry, promptLoader, sseEmitter
  agents/connectors/    executor.js — generic connector runner (sql/http/internal), tool-def builder, audit logger
  mcp/                  mcpServer.js(JSON-RPC transport), toolProvider.js(discovery), toolExecutor.js(dispatch + fuzzy search)
  utils/                scoring(PCMH/RAF), fhirConverters(CEE), extraction, diagnosis/dos inserts, claude client, hcc, clinical*
  db/                   database.js(better-sqlite3 handle), migrate.js(sequential .sql runner), seed.js, migrations/*.sql (001–025)
client/
  src/api/              axios layer (index.ts base + per-domain *Api.ts)
  src/pages/{payer,admin,provider}/  route pages
  src/{components,context,hooks,types,utils}/
```

## 3. API ROUTES
All mounted in `server/index.js:92-131`. Auth = JWT `authMiddleware` unless noted. `success/data/error` envelope.

| Mount | METHOD path | handler | purpose |
|---|---|---|---|
| `/api/auth` | POST /login, /logout | `routes/auth.js:4-5` → controllers/authController | JWT login (bcrypt) |
| `/api/members` | GET / POST / | `routes/members.js:28-29` | list/create members |
| | GET /:id | `members.js:30` | member detail |
| | GET /:id/scoring-explanation | `members.js:31` | PCMH tier trace |
| | GET/POST /:id/diagnoses | `members.js:51-52` | list/add dx |
| | GET /:id/labs, /medications, /dates-of-service, /care-plan, /communications, /attachments, /care-circle | `members.js:50-65` | clinical sub-resources |
| | POST /:id/voice-call(+/preview) | `members.js:79-98` | Telnyx outbound |
| `/api/members` (memberChat) | POST /:id/chat | `routes/memberChat.js:34` | member AI chat |
| `/api/members` (charlie) | POST /:id/charlie/chat(+/stream), GET /:id/charlie/connectors | `routes/charlie.js:17-112` | Charlie tool-using assistant (SSE stream) |
| `/api/members` (customAgents) | POST /:memberId/custom-agent/:agentName/chat(+/stream) | `routes/customAgents.js:14-53` | DB-defined custom agent chat |
| `/api/members` (careTeam/appointments) | GET/POST/DELETE care-team, appointments | `memberCareTeam.js`, `appointments.js` | |
| `/api/messages` | POST /, GET /:id, /:id/conversation, PUT /:id/read, POST /:id/followup, /:id/extract, /:id/apply | `routes/messages.js:9-15` | secure messaging + extraction-apply |
| `/api/provider` | GET /session/:token, POST /otp/send, /otp/verify, GET/POST /session/:token/chat, POST /session/:token/done | `routes/provider.js:6-11` | provider portal (OTP, no JWT) |
| `/api/chat` | GET /:session_id/messages | `routes/chat.js:7` | chat history |
| `/api/sms` | GET /templates, /:member_id; POST /send, /optin; PUT /:member_id/consent | `routes/sms.js:8-12` | SMS |
| `/api/care-plan` | PUT/DELETE /tasks/:id | `routes/carePlan.js:8-9` | care plan tasks |
| `/api` (agents) | GET /agents/stream(SSE, no auth), POST /agents/run, GET /agents/runs(+/:id,/:id/actions), GET/PUT /agents/schedule, GET /alerts, PUT /alerts/:id/{read,resolve}, GET /members/:memberId/suggestions, PUT /suggestions/:id/{accept,dismiss} | `routes/agents.js:13-220` | agent orchestration + Compass suggestions |
| `/api/x12` | POST /837, /835, /278 (`requireApiKey`), GET /status/:document_id, /samples | `routes/x12.js:12-62` | X12 ingest (API-key auth) |
| `/api` (admin) | GET /admin/entity-counts, /admin/events(+/summary), PUT /admin/events/:id/resolve, DELETE /admin/events/clear | `routes/admin.js:7-194` | admin metrics/event queue |
| `/api/claims` | GET / | `routes/claims.js:9` | claims list |
| `/api/documents` | GET /:id | `routes/documents.js:8` | document fetch |
| `/api/guidelines` | GET / POST / PUT /:id, GET /:id, POST /:id/criteria, DELETE /criteria/:id | `routes/guidelines.js:9-78` | LCD/NCD guidelines |
| `/api/prior-auth` | GET / POST / GET /:id, POST /:id/decide | `routes/priorAuth.js:20-129` | prior-auth workflow |
| `/api/admin/agents` | GET / POST / GET/PUT/DELETE /:name, GET /custom/list | `routes/adminAgents.js:47-169` | agent CRUD (prompts + custom agents) |
| `/api/admin/tools` | GET / GET /:id, POST /, PUT /:id, DELETE /:id, PATCH /:id/toggle, POST /:id/test | `routes/adminTools.js:19-138` | **connector/tool CRUD + live test** |
| `/api/admin/settings` | GET/PUT /scoring, POST /scoring/preview, /scoring/recompute-all, GET/PUT /platform | `routes/settings.js:85-201` | scoring weights + platform flags |
| `/api/intake` | POST /upload, POST /confirm | `routes/intake.js:108,200` | **PDF intake → fuzzy member match → confirm/link/create** |
| `/api/webhooks` | POST /telnyx(raw), /telnyx/voice, /telnyx/voice/gather/:call_id, /telnyx/voice/status | `routes/webhooks.js:12-213` | Telnyx SMS/voice (raw body, pre-json) |
| `/mcp` | (MCP server) see §5 | `mcp/mcpServer.js` | **MCP JSON-RPC + REST** (X-API-Key) |
| `/api/clearlink` | POST /add-diagnosis | `routes/mcpTools.js:28` | **add ICD-10 dx to member (LLM-validated)** — ⚠ NO auth middleware applied |
| (top-level) | GET /api/health, /api/platform-overview, /api/providers(+/:id,/:id/calls), /api/lookup/icd-hcc, /api/audit/:entity_type/:entity_id | `index.js:87-131` | health + lookups (authMiddleware on lookups) |

## 4. DATA MODELS (SQLite — `server/db/migrations/*.sql`)
Schema built by sequential `.sql` migrations (`migrate.js`), tracked in `schema_migrations`. Migrations 001–025; `agent_tools` created in 016, **extended in 025**.

**Core / highlighted tables:**

| Table | Key columns | Purpose |
|---|---|---|
| **members** | id PK, first_name, last_name, dob, member_id UNIQUE, patient_id, insurance_plan, phone_number, sms_consent, status, pcp_id→providers, risk_score, risk_level, raf_score | member master. `members.id`=internal int; `members.member_id`=external MRN string. Fuzzy search + intake target. |
| **diagnoses** | id, member_id→members, icd10_code→icd_hcc_lookup, description, hcc_code, raf_weight, date_diagnosed, status; UNIQUE(member_id,icd10_code) | member dx; drives RAF |
| icd_hcc_lookup | icd10_code UNIQUE, description, hcc_code, hcc_description, raf_weight, category, is_hcc | ICD→HCC ref; auto-extended by add-diagnosis LLM lookup (`mcpTools.js:100`) |
| medications, labs, dates_of_service | member_id FK + clinical fields + source_type/source_id/source_ref | clinical sub-records |
| **documents** | id, member_id→members(nullable), doc_type, raw_content, parsed_json, source_ref, created_at (+ `cee_json` via migration) | uploaded docs / intake corpus. Intake inserts with member_id NULL then links (`intake.js:131,239`) |
| claims | id, member_id, document_id, claim_number, claim_type, claim_status, service_from/to, total_charge, total_paid, payer_claim_id, provider_npi, provider_name, diagnosis_codes, compass_flags, compass_run_at | claims (837/835 ingest) |
| claim_lines, claim_flags | — | claim detail + Compass flags |
| **agent_tools** | id, name, description, **endpoint_url NOT NULL**, http_method DEFAULT 'POST', auth_header_name, auth_header_format, api_key, additional_headers, request_body_schema, enabled DEFAULT 1, **kind DEFAULT 'http'**(http/sql/internal), **sql_template**, **input_schema**(JSON), **mock_enabled**, **mock_response**, **for_agents** (CSV of agent names), UNIQUE(name) | **connector/tool registry — backs BOTH MCP tools and Charlie connectors.** Extended cols added by 025. |
| **agent_tool_calls** | id, agent_name, member_id→members, tool_name, input_json, output_json, ok, error_message, duration_ms, user_id→users, created_at | **audit trail of every tool/connector execution** (MCP logs agent_name='MCP'; Charlie logs 'CHARLIE') |
| api_keys | id, key_hash UNIQUE(sha256), label, permissions(JSON, default `["read"]`), is_active, last_used_at | API-key auth for x12 + (intended) MCP REST |
| agent_configs | id, agent_name UNIQUE, system_prompt, +(025/023) is_custom, model DEFAULT 'claude-sonnet-4-6', icon, color, full_name, role | agent prompt overrides + custom agent defs |
| agent_runs / agent_actions / nurse_alerts / compass_suggestions | run/action/alert/suggestion rows | agent scheduler audit + UI surfaces (`agentLogger.js`) |
| audit_log | entity_type, entity_id, action, performed_by, performed_by_type, details(JSON) | entity-level audit (`agentLogger.auditLog`) |
| users | auth users (bcrypt) | |
| providers, member_providers, member_accumulators, benefit_plans, benefit_categories, prior_authorizations, guidelines, guideline_criteria, guideline_sources, secure_messages, conversations, sms_messages, message_extractions, voice_calls, provider_calls, care_plans, care_plan_tasks, care_circle_contacts, appointments, chat_sessions, event_queue, herald_events, member_agent_prefs, system_configs, agent_schedules, schema_migrations | supporting tables |

## 5. MCP SYSTEM (reference implementation — deep)

**Transport** (`server/mcp/mcpServer.js`, Express router mounted at `/mcp`):
- Auth: `validateApiKey` (`mcpServer.js:12`) requires header **`X-API-Key` == `process.env.MCP_API_KEY`**; 401 on mismatch, 500 if unset.
- `POST /mcp/rpc` (`:44`) — **JSON-RPC 2.0**. Methods:
  - `tools/list` → `{ tools: getAllMcpTools() }` (`:59`)
  - `tools/call` → `{ name, arguments }` → `executeMcpTool(name, args)`; returns `{success:true, data}` (`:64-81`)
  - errors → JSON-RPC `error` objects (codes -32600/-32603).
- REST conveniences: `GET /mcp/health` (`:39`), `GET /mcp/tools` (`:107`), `POST /mcp/tools/:name/call` (`:116`).

**Discovery** (`server/mcp/toolProvider.js`):
- `loadMcpTools()` (`:13`) — `SELECT … FROM agent_tools WHERE enabled=1 ORDER BY name`; parses `input_schema` JSON.
- `getToolByName(name)` (`:37`) — full row by name, enabled=1.
- `toolToMcpTool(tool)` (`:64`) — converts to MCP shape `{name, description, inputSchema}`. **Injects a required `member_id` string property** into every tool's schema EXCEPT `noMemberIdTools = {search_members, add_diagnosis}` (`:68`).
- `getAllMcpTools()` (`:94`) — list → MCP defs.

**Dispatch** (`server/mcp/toolExecutor.js`):
- `executeMcpTool(toolName, input)` (`:72`):
  1. `getToolByName` → 404-style `{ok:false}` if missing.
  2. If `input.member_id` present → resolves external MRN → internal `members.id` (`:85`); 404 if not found.
  3. Special-case `search_members` → `fuzzySearchMembers(query)` (LLM path, `:115`).
  4. Else builds a connector object from the row and calls `runConnector` (`:130`).
  5. **Logs every call to `agent_tool_calls`** with `agent_name='MCP'` (`:120,134`).

**Fuzzy member search (CANONICAL)** — `fuzzySearchMembers(query)` (`toolExecutor.js:11`):
- `SELECT id, member_id, first_name, last_name FROM members` (all rows).
- Builds Markdown roster, prompts Claude as a "medical records clerk" to return a JSON array of internal IDs; handles typos, reversed names, nicknames, partial.
- **Direct axios POST to `https://api.anthropic.com/v1/messages`** (`:37`), model `process.env.ANTHROPIC_MODEL_SMART || 'claude-sonnet-4-6'`, max_tokens 256, headers `x-api-key`/`anthropic-version:2023-06-01`.
- Parses array, filters pre-fetched rows by ID; JSON-parse failure → empty `[]`.
- Twin impl for intake: `findMemberMatches(demographics)` in `routes/intake.js:27` (same axios/model/prompt pattern, returns `{exact, fuzzy}` using name+DOB+MemberID).

**Tool name → backing impl (live DB `agent_tools`):**
| tool | kind | backing | for_agents |
|---|---|---|---|
| `search_members` | (special) | LLM fuzzy `toolExecutor.js:11` — ⚠ **no enabled DB row present in live db**; code path exists, tool currently NOT listed by `tools/list` | — |
| `add_diagnosis` | http | POST `…/api/clearlink/add-diagnosis` (`routes/mcpTools.js:28`) | — |
| `explain_pcmh_tier` | internal | `INTERNAL_CONNECTORS.explain_pcmh_tier` → `scoringUtils.explainMemberScoring` (`connectors/executor.js:14`) | CHARLIE |
| `get_member_demographics`, `list_diagnoses`, `list_medications`, `list_dates_of_service`, `get_claims_window`, `get_labs_window`, `get_provider_messages`, `list_prior_authorizations` | sql | `sql_template` via `runSqlConnector` (named `:param` binds) | CHARLIE |
| `get_socioeconomic_profile` | http | external `https://sdoh.example.com/...` (demo) | CHARLIE |

**Env vars:** `MCP_API_KEY` (transport auth), `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL_SMART` (default `claude-sonnet-4-6`), `ANTHROPIC_MODEL_FAST` (`claude-haiku-4-5-20251001`). `.env.mcp.example` documents MCP_API_KEY + optional MCP_HOST/MCP_PORT (MCP runs in-process on main PORT, **not** a separate port — doc mentions 8010 as override).

## 6. AGENT / CONNECTOR FRAMEWORK

**`runConnector(connector, input)`** (`server/agents/connectors/executor.js:143`):
- Validates `input` against `connector.input_schema` via `validateInput` (`:29`) — minimal JSON-Schema subset (type/required/enum/min/max/additionalProperties; no Ajv). Returns `{ok, data|error, duration_ms}`.
- Dispatch by `kind`:
  - **`sql`** → `runSqlConnector` (`:68`): extracts `:param` placeholders, binds from input, `db.prepare(sql).all(binds)` → `{rows, count}`.
  - **`http`** → `runHttpConnector` (`:105`): if `mock_enabled` returns parsed `mock_response` JSON (`mocked:true`); else interpolates `{placeholder}` in URL, builds auth header (`auth_header_name` + `auth_header_format` with `{key}`→`api_key`), merges `additional_headers`, axios call (timeout 30s).
  - **`internal`** → `runInternalConnector` (`:90`): `endpoint_url` sentinel `internal://<fn>` keyed into `INTERNAL_CONNECTORS` map (`:13`).
- `connectorToToolDef(connector)` (`:168`) → Claude tool def `{name, description, input_schema}`.
- `loadConnectorsForAgent(agentName)` (`:177`) — enabled tools where `for_agents` empty/NULL OR CSV contains the agent name.
- `getConnectorByName` (`:186`), `logToolCall(row)` (`:190`) → INSERT into `agent_tool_calls` (full audit incl member_id, user_id, duration).

**Charlie tool-use loop** (`server/agents/charlie.js`):
- Native Anthropic tool-use loop, **direct axios** to `https://api.anthropic.com/v1/messages` (`:21,57`), `MAX_ITERATIONS=8`, max_tokens 2048.
- `buildTools(agentName)` (`:48`) = `loadConnectorsForAgent` → `connectorToToolDef` + built-in **`ask_user`** tool (`:27`, short-circuits loop, returns question+2–4 options to UI, never executed server-side).
- `executeTool` (`:78`): `getConnectorByName` → **pins `member_id` from URL path, never trusts model** (`:104`); runs connector, logs to `agent_tool_calls`, feeds `tool_result` (with `is_error`) back to Claude. Stateless (client resends full history). Streaming variant emits via `sseEmitter`.

**Named agents** (`server/agents/agentRegistry.js`): ARIA, ECHO, RELAY, PULSE, COMPASS, VERO, SENTINEL, SCRIBE, CHARLIE (9). Plus `dynamicAgent.js` (DB-defined custom agents via `agent_configs.is_custom`), `scheduler.js` (node-cron, `initScheduler()` at `index.js:147`), `promptLoader.js` (prompt overrides from `agent_configs`), `sseEmitter.js` (server-sent events), `clinicalContextBuilder.js`.

**Audit** (`server/agents/agentLogger.js`): `logStep`/`updateStep` (agent_actions), `createNurseAlert` (nurse_alerts + SSE), `createCompassSuggestion` (compass_suggestions, cap 7/member, dedup by title), `auditLog(entityType, entityId, action, performedBy, details)` (audit_log; non-fatal try/catch). ⚠ **Signature mismatch:** `mcpTools.js:143` calls `auditLog({object})` but `agentLogger.auditLog` expects positional args — the MCP add-diagnosis audit row is malformed/silently dropped.

## 7. SERVICES & UTILS
| File | Responsibility |
|---|---|
| `services/pdfService.js` | pdfjs-dist text extraction (`extractText(buffer)`) |
| `services/extractionPipeline.js` | orchestrates clinical extraction (dx/meds/labs/DOS/care-plan) from CEE → structured (Sentinel) |
| `services/claudeService.js` | Claude calls for service-layer LLM tasks |
| `services/x12Service.js`, `x12_278Service.js` | X12 837/835/278 parse + persist |
| `services/insightsService.js` | member insights generation |
| `services/documentService.js`, `messageService.js`, `activityService.js` | document/message/activity helpers |
| `services/smsService.js`, `voiceService.js`, `voiceScriptService.js`, `emailService.js`, `otpService.js`, `tokenService.js` | comms + secure-link/OTP/JWT issuance |
| `utils/scoringUtils.js` | PCMH risk stratification + CMS-HCC RAF; `updateMemberScores`, `explainMemberScoring` (Charlie internal connector) |
| `utils/fhirConverters.js` | PDF/text → **CEE (Clinical Evidence Envelope)** `fromPDFToCEE` |
| `utils/extractionUtils.js` | `extractDemographics` (LLM) + extraction helpers |
| `utils/diagnosisUtils.js` / `dosUtils.js` | `safeInsertDiagnosis` / `safeInsertDOS` (idempotent inserts w/ source provenance) |
| `utils/claudeClient.js` | **Anthropic SDK** wrapper (`new Anthropic()`): `callClaude` (default model `claude-opus-4-8`), `verifyIcd10Code`, `getIcd10Details` (used by add-diagnosis) |
| `utils/hccUtils.js`, `clinicalClassifier.js`, `clinicalEnvelope.js`, `claimsUtils.js`, `memberUtils.js`, `parseClaudeJson.js`, `eventLogger.js` | HCC math, pure clinical classification, CEE schema, claim/member helpers, robust JSON parsing, event_queue logger |

## 8. EXTERNAL INTEGRATIONS
**Outbound:**
| Target | Where | Auth/env |
|---|---|---|
| Anthropic Messages API (direct axios) | `mcp/toolExecutor.js:37`, `routes/intake.js:64`, `agents/charlie.js:21,57` | `ANTHROPIC_API_KEY`, model `ANTHROPIC_MODEL_SMART` |
| Anthropic (SDK `@anthropic-ai/sdk`) | `utils/claudeClient.js:3` (`new Anthropic()`), `services/claudeService.js`, `services/extractionPipeline.js` | `ANTHROPIC_API_KEY` (SDK env), model `claude-opus-4-8` default |
| Telnyx voice/SMS | `services/voiceService.js`, `services/smsService.js`, `routes/webhooks.js` | `TELNYX_*`, `VOICE_CALL_ENABLED` |
| EmailJS | `services/emailService.js` | `EMAILJS_*` |
| HTTP connectors (e.g. SDOH demo) | `connectors/executor.js:105` per-tool `endpoint_url`/`api_key` | per-row |

**Inbound (who calls clearlink):** OPA backend (`/Users/issamzeinoun/claude/overcoding/opa/server`):
- `app/routes/clearlink_proxy.py:141` → **POST `{CLEARLINK_MCP_URL}/api/clearlink/add-diagnosis`** with `Authorization: Bearer {CLEARLINK_API_KEY}` (⚠ that clearlink route applies **no** auth middleware — Bearer ignored).
- `app/services/assistant/clearlink_integration.py` → ClearLink **MCP** at `CLEARLINK_MCP_URL` (e.g. `http://localhost:8010/mcp`), JSON-RPC `tools/list` + `tools/call` with `X-API-Key`=`CLEARLINK_MCP_API_KEY` (== clearlink's `MCP_API_KEY`). Surfaced to the OPA assistant as dynamic ClearLink tools.

## 9. AUTH
- **JWT (`middleware/authMiddleware.js`):** `Authorization: Bearer <jwt>`, `jwt.verify` with `JWT_SECRET` (default `'changeme_in_production'`), sets `req.user`. Used on most `/api/*` routers. Frontend stores token in `localStorage('clearlink_token')`, auto-redirects to /login on 401 (`client/src/api/index.ts`).
- **API-key (`middleware/apiKeyMiddleware.js`):** `requireApiKey(permissions[])` — `Authorization: Bearer <key>`, sha256 → `api_keys.key_hash` lookup, permission check vs `api_keys.permissions`, updates `last_used_at`. Used on `/api/x12/*`.
- **MCP API key (`mcp/mcpServer.js:12`):** header `X-API-Key` == `MCP_API_KEY` env (separate from api_keys table).
- **Provider portal:** OTP/secure-link (`otpService`, `tokenService`), no JWT.
- ⚠ `/api/clearlink/add-diagnosis` has **no auth** (publicly callable if reachable). `/api/agents/stream` SSE also unauthenticated.

## 10. CONFIG & ENV
| Var | Purpose / default |
|---|---|
| `PORT` | server port (.env=**8010**; example 3000) |
| `NODE_ENV` | dev/production (prod serves `client/dist`) |
| `DB_PATH` | `./data/clearlink.db` |
| `JWT_SECRET` / `JWT_EXPIRY` | JWT signing / `8h` |
| `ANTHROPIC_API_KEY` | Claude auth (axios + SDK) |
| `ANTHROPIC_MODEL_SMART` | `claude-sonnet-4-6` (fuzzy search, intake, Charlie) |
| `ANTHROPIC_MODEL_FAST` | `claude-haiku-4-5-20251001` |
| `MCP_API_KEY` | MCP `X-API-Key` (no default; 500 if unset) |
| `BASE_URL` / `ALLOWED_ORIGINS` | CORS (note `/api/*` also sets `Access-Control-Allow-Origin:*` — `index.js:69`) |
| `OTP_EXPIRY_MINUTES`, `OTP_GRACE_PERIOD_HOURS`, `TOKEN_EXPIRY_HOURS` | provider session |
| `EMAILJS_*`, `TELNYX_*`, `VOICE_CALL_ENABLED` | comms |
- Config files: `.env`, `.env.example`, `.env.mcp.example`, `nixpacks.toml`, `railway.toml`, `.dockerignore`.

## 11. FRONTEND (`client/`)
- React + TS + Vite + Tailwind. `client/src/App.tsx`, `main.tsx`.
- **API layer** `client/src/api/`: `index.ts` = axios instance, `baseURL = VITE_API_URL || ''` (same-origin in prod), `withCredentials`, injects `Bearer` from `localStorage('clearlink_token')`, 401 → redirect /login. Per-domain: `authApi, membersApi, providersApi, providerApi, messagesApi, smsApi, chatApi, agentsApi, adminApi, intakeApi`.
- **Pages** `client/src/pages/`:
  - `payer/`: Dashboard, Members, MemberDetail, Claims, Cases, Messages, PriorAuth, Providers, Reports, Settings, AgentMonitor, About, Login.
  - `admin/`: AdminTools (connector CRUD UI), Guidelines, Monitoring, Architecture.
  - `provider/`: ProviderVerify, ProviderSession, ProviderDone (OTP portal).
- `components/`, `context/`, `hooks/`, `types/`, `utils/`.

## 12. KNOWN ISSUES / GAPS / TODOs
1. **`search_members` half-wired:** LLM fuzzy code exists (`toolExecutor.js:11`) and is in `noMemberIdTools`, but **no enabled `agent_tools` row** in the live DB — so `tools/list` does NOT advertise it and `executeMcpTool('search_members')` returns "Tool not found". To expose, insert an `agent_tools` row named `search_members`. (Canonical logic is present; registration is missing.)
2. **add-diagnosis is unauthenticated** (`routes/mcpTools.js` imports `requireApiKey` but never applies it). OPA sends Bearer but it's ignored.
3. **auditLog signature mismatch** at `mcpTools.js:143` (object arg vs positional `agentLogger.auditLog`) → MCP dx audit log silently malformed.
4. **Two divergent Claude call styles:** direct axios (`anthropic-version:2023-06-01`, model from env) vs SDK (`claudeClient.js`, hardcoded `claude-opus-4-8`). No single client; model defaults differ (`claude-sonnet-4-6` vs `claude-opus-4-8`). Model ids in `.env.example` (`claude-sonnet-4-20250514`) differ from `.env` (`claude-sonnet-4-6`).
5. **CORS wide-open:** `/api/*` sets `Access-Control-Allow-Origin: *` (`index.js:69`) regardless of `ALLOWED_ORIGINS`.
6. **MCP "separate port" doc gap:** `.env.mcp.example` implies MCP_HOST/MCP_PORT 8010; actual impl mounts MCP in-process on main `PORT` (`index.js:118`). No standalone MCP transport (no stdio; HTTP JSON-RPC only).
7. **No Ajv:** connector input validation is a hand-rolled subset (`executor.js:29`), deferred to "production phase".
8. **Migrations are append-only ALTERs** with duplicate-column swallowing (`migrate.js:43`); no down-migrations; root `clearlink.db` is a stale checked-in artifact.

---
### DUPLICATION vs OPA (shared logic to consolidate)
- **LLM fuzzy member matching:** clearlink `fuzzySearchMembers`/`findMemberMatches` (canonical) vs OPA `intake_matching_service.py` / member matching — same "roster → Claude clerk → IDs" pattern.
- **PDF intake → extract → match → persist:** clearlink `routes/intake.js` + `extractionPipeline` vs OPA `prepay_intake_service.py` / `ai_service.py`.
- **ICD-10 validation / HCC lookup:** clearlink `claudeClient.verifyIcd10Code`/`getIcd10Details` vs OPA detector/code seed catalogues.
- **Claim scoring:** clearlink Compass flags (`compass_flags`) vs OPA detectors/posterior.
- **Add-diagnosis is the integration seam:** OPA → clearlink (don't reimplement in OPA).
