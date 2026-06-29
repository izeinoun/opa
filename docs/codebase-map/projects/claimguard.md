# CLAIMGUARD — Machine-Readable Codebase Map

> Generated: 2026-06-29. Profiles the CURRENT state of the claimguard frontend and merger gaps relative to opa/CLAUDE.md Phase-2 plan.

---

## 1. IDENTITY

| Field | Value |
|---|---|
| **Project root** | `/Users/issamzeinoun/claude/claimguard` |
| **Purpose** | Pre-pay (ClaimGuard) claim review UI — React SPA for intake, triage, AI-findings review, denial/approval packaging |
| **Stack** | React 19, Vite 8, TypeScript ~6, Tailwind 3, Axios, pdfjs-dist, react-markdown |
| **Entrypoint** | `frontend/src/main.tsx` → `App.tsx` |
| **Dev port** | `5175` (pinned in `frontend/vite.config.ts:8`) |
| **Prod port** | `$PORT` via `npm run start` (`serve -s dist`) |
| **API target (dev)** | `http://localhost:8001` — OPA backend (set in `frontend/src/config/appUrls.ts:24`) |
| **API target (prod)** | `https://payguard.penguinai.studio` (same OPA backend; `appUrls.ts:15`) |
| **Run scripts** | `npm run dev` / `npm run build` / `npm run start` (`frontend/package.json:6-11`) |
| **Railway deploy** | `frontend/railway.json` — Railpack, build `npm run build`, start `npm run start`, healthcheck `/` |
| **Merger status** | BACKEND fully ported into OPA (Phase 1 complete). FRONTEND: API layer re-pointed to OPA (Phase 2 substantially done), but 3 deferred endpoints and 2 broken export paths remain (see §8). Standalone ClaimGuard backend at `/Users/issamzeinoun/claude/claimguard/backend/` is RETIRED (targeted for deletion in Phase 3). |
| **Old standalone backend port** | `:8002` (referenced only in `scripts/prewarm.sh`) |

---

## 2. STRUCTURE

```
claimguard/
├── frontend/
│   ├── src/
│   │   ├── main.tsx                    — React root; wraps App with <DemoGate>
│   │   ├── App.tsx                     — BrowserRouter + route table + <NoAccessGate>
│   │   ├── DemoGate.tsx                — HMAC demo-password gate (OPA /api/auth/login)
│   │   ├── api/
│   │   │   ├── client.ts               — Axios instance; injects X-User-Id + Bearer token
│   │   │   ├── index.ts                — All OPA API calls + OPA→CG shape adapters
│   │   │   └── types.ts                — Canonical TS types (UUID id, OPA-aligned fields)
│   │   ├── config/
│   │   │   └── appUrls.ts              — Hard-coded URL map by Vite build mode (no env vars)
│   │   ├── context/
│   │   │   └── AppContext.tsx          — Global: users, currentUser, config, refresh
│   │   ├── services/
│   │   │   └── authService.ts          — Cookie-based auth service (getCurrentUser / login / logout / refresh / BroadcastChannel)
│   │   ├── components/
│   │   │   ├── Layout.tsx              — Shell: sidebar nav, queue badges, assistant toggle
│   │   │   ├── AppTopBar.tsx           — User switcher + cross-app links (IAM/PayGuard/SIU)
│   │   │   ├── AssistantPanel.tsx      — SSE chat panel → /api/assistant/chat/stream
│   │   │   ├── Avatar.tsx              — Initials/color avatar using User.initials + color_hex
│   │   │   ├── Button.tsx              — Shared button component
│   │   │   ├── DemoGate.tsx            — (imported in main.tsx, not here)
│   │   │   ├── EnvironmentBanner.tsx   — Non-prod banner (VITE_ENVIRONMENT check)
│   │   │   ├── ErrorBoundary.tsx       — React error boundary
│   │   │   ├── Modal.tsx               — Generic modal wrapper
│   │   │   ├── NoAccessGate.tsx        — RBAC: checks currentUser.apps includes "claimguard"
│   │   │   ├── Spinner.tsx             — Loading spinner
│   │   │   ├── StatusBadge.tsx         — Claim status pill
│   │   │   ├── SupervisorOnly.tsx      — Role gate (supervisor|admin)
│   │   │   ├── AdminOnly.tsx           — Role gate (admin)
│   │   │   ├── Toaster.tsx             — Toast notifications
│   │   │   └── claim-detail/
│   │   │       ├── ClaimActionsBar.tsx         — Primary action buttons (approve/deny/escalate/SIU)
│   │   │       ├── ClaimSummaryCard.tsx        — Claim header card (patient/provider/DOS/amounts)
│   │   │       ├── ClaimFormSection.tsx        — Claim lines table (CPT, units, billed)
│   │   │       ├── TabAIFindings.tsx           — AI findings list + accept/reject decisions
│   │   │       ├── TabComments.tsx             — Comments thread → /api/prepay/claims/{id}/comments
│   │   │       ├── TabDocuments.tsx            — PDF upload/view/delete → /api/documents
│   │   │       ├── TabClaimDetails.tsx         — ICD/CPT breakdown
│   │   │       ├── TabAuditTrail.tsx           — Audit log display
│   │   │       ├── TabEvidence.tsx             — Code evidence scanner (per ICD/DRG)
│   │   │       ├── TopBar.tsx                  — Claim-detail breadcrumb + back button
│   │   │       ├── ApprovalExportModal.tsx     — ZIP approval package → BROKEN PATH (see §8)
│   │   │       ├── DenialPackageModal.tsx      — ZIP denial package → BROKEN PATH (see §8)
│   │   │       ├── FindingsLetterModal.tsx     — Provider letter generation
│   │   │       ├── MessageProviderModal.tsx    — Provider message → NOT PORTED endpoint
│   │   │       ├── PdfHighlightViewer.tsx      — pdf.js viewer with text highlight
│   │   │       ├── PdfViewerModal.tsx          — pdf.js inline viewer modal
│   │   │       ├── ReasonActionModal.tsx       — Generic reason-entry modal
│   │   │       ├── ReassignModal.tsx           — Claim reassignment → /api/prepay/claims/{id}/assign
│   │   │       ├── SendToSiuModal.tsx          — SIU referral → /api/prepay/claims/{id}/send-to-siu
│   │   │       └── SetOutcomeModal.tsx         — Status transition modal
│   │   ├── lib/
│   │   │   ├── format.ts               — formatCurrency, formatDate, billedAmountClass
│   │   │   └── queues.ts               — QUEUES config + queueByKey/statusInQueue helpers
│   │   └── pages/
│   │       ├── Dashboard.tsx           — KPI/status/aging/workload tiles → /api/prepay/dashboard[/me]
│   │       ├── ClaimsQueue.tsx         — Filtered claim list with queue tabs
│   │       ├── ClaimDetail.tsx         — Tabbed claim detail page
│   │       ├── NewClaim.tsx            — Manual claim creation form
│   │       ├── FileIntake.tsx          — Admin drop-folder ingestion → /api/file-intake/*
│   │       ├── UnmatchedDocuments.tsx  — Admin unmatched intake resolver
│   │       ├── TeamMonitor.tsx         — Supervisor live queue overview
│   │       ├── Reports.tsx             — Specialist/summary reports → /api/prepay/reports/*
│   │       ├── Members.tsx             — Members directory → /api/members
│   │       ├── Admin.tsx               — Operator config → /api/runtime-config
│   │       └── Placeholder.tsx         — Stub for unimplemented routes
│   ├── vite.config.ts                  — port 5175, strictPort
│   ├── package.json                    — deps + scripts
│   ├── railway.json                    — Railway deploy config
│   └── index.html                      — HTML entrypoint
├── scripts/
│   ├── prewarm.sh                      — Pre-generate AI findings/summary/codes on seeded claims (TARGETS OLD BACKEND :8002)
│   └── build_overview_pptx.py          — Generates ClaimGuard_AI_Customer_Deck.pptx (python-pptx)
├── CLAUDE.md                           — Dev guidance (describes OLD standalone backend — superseded for backend concerns)
├── DATABASE.md                         — Old DB schema docs (standalone backend — retired)
├── README.md                           — User-facing flows + old Railway runbook
├── CMS-1500_Dorothy_Hawkins.pdf        — Test fixture
├── UB-04_Dorothy_Hawkins.pdf           — Test fixture
├── dorothy_hawkins_medical_record.pdf  — Test fixture
├── dorothy_hawkins_medical_record.txt  — Test fixture (text)
├── john_doe_readmission_MR.pdf         — Test fixture
└── ClaimGuard_AI_Customer_Deck.pptx    — Output of build_overview_pptx.py
```

---

## 3. PAGES / ROUTES

| Route | Component file:line | Purpose |
|---|---|---|
| `/` | `pages/Dashboard.tsx:1` | KPI cards, status distribution, aging buckets, AI coverage, specialist workload |
| `/claims` | `pages/ClaimsQueue.tsx:1` | Filterable claim list; queue tabs driven by `lib/queues.ts:QUEUES` |
| `/claims/new` | `pages/NewClaim.tsx:1` | Manual claim form + PDF drag-and-drop intake |
| `/claims/:id` | `pages/ClaimDetail.tsx:1` | Tabbed detail: Summary / AI Findings / Evidence / Comments / Documents / Audit Trail |
| `/team` | `pages/TeamMonitor.tsx:1` | Supervisor-only: live queue status per analyst |
| `/reports` | `pages/Reports.tsx:1` | Summary stats + per-specialist breakdown; CPT/DRG filter |
| `/members` | `pages/Members.tsx:1` | Read-only member directory with LOB filter + pagination |
| `/file-intake` | `pages/FileIntake.tsx:1` | Admin-only: upload 835/837/medical/claim PDFs to OPA intake |
| `/file-intake/unmatched` | `pages/UnmatchedDocuments.tsx:1` | Admin-only: resolve unmatched ingested files to cases |
| `/admin` | `pages/Admin.tsx:1` | Supervisor+: edit runtime config keys (ai_suggestions_enabled, threshold, etc.) |

Route guards: `SupervisorOnly` wraps `/team`, `/admin`; `AdminOnly` wraps `/file-intake*`; `NoAccessGate` wraps entire app checking `user.apps.includes("claimguard")`.

---

## 4. API LAYER

### Base URL config
- Source: `frontend/src/config/appUrls.ts:14-35`
- Dev: `http://localhost:8001` (OPA backend — already re-pointed)
- Prod: `https://payguard.penguinai.studio` (OPA backend)
- NOT read from `VITE_*` env vars by design (`appUrls.ts:8-13`)
- Injected into Axios via `frontend/src/api/client.ts:8` (`baseURL: API_BASE_URL`)

### Request interceptor (`frontend/src/api/client.ts:12-27`)
- Reads `localStorage.getItem("claimguard.currentUserId")` → `X-User-Id` header
- Reads `localStorage.getItem("opa_demo_token")` → `Authorization: Bearer` header
- Response interceptor: 401 on non-auth URLs → clear token + `window.location.reload()`

### All endpoints (all hit OPA :8001 unless flagged OLD)

| Caller | Method | Path | OPA/OLD | Notes |
|---|---|---|---|---|
| `api.listUsers()` | GET | `/api/users` | OPA | Returns `User[]`; `analyst` role adapted to `specialist` |
| `api.getUser(id)` | GET | `/api/users/{id}` | OPA | |
| `api.listClaims(filters)` | GET | `/api/prepay/claims` | OPA | Client-side filter for assigned_to, cpt, drg, above_threshold |
| `api.getClaim(id)` | GET | `/api/prepay/claims/{id}` | OPA | Returns `OpaPrepayClaimDetail` adapted to `ClaimDetail` |
| `api.createClaim(payload)` | POST | `/api/prepay/claims` | OPA | Manual intake |
| `api.createFromPdf(file)` | POST | `/api/prepay/claims/from-pdf` | OPA | multipart/form-data; 90s timeout |
| `api.updateStatus(...)` | PATCH | `/api/prepay/claims/{id}/status` | OPA | |
| `api.sendToSiu(...)` | POST | `/api/prepay/claims/{id}/send-to-siu` | OPA | |
| `api.reassign(...)` | PATCH | `/api/prepay/claims/{id}/assign` | OPA | |
| `api.addComment(...)` | POST | `/api/prepay/claims/{id}/comments` | OPA | |
| `api.recheck(...)` | POST | `/api/prepay/claims/{id}/recheck` | OPA | |
| `api.generateSummary(...)` | POST | `/api/prepay/claims/{id}/summary` | OPA | |
| `api.generateCodeDescriptions(...)` | POST | `/api/prepay/claims/{id}/code-descriptions` | OPA | |
| `api.rerunAnalysis(...)` | POST | `/api/prepay/claims/{id}/run-detectors` | OPA | |
| `api.updateCaseStatus(...)` | PATCH | `/api/prepay/claims/{id}/case-status` | OPA | |
| `api.messageProvider(...)` | POST | `/api/prepay/claims/{id}/messages` | **UNPORTED** | Endpoint NOT implemented in OPA (CLAUDE.md deferred list) |
| `api.searchEvidence(...)` | GET | `/api/prepay/claims/{id}/evidence?q=` | **UNPORTED** | Text search NOT ported to OPA |
| `api.setFindingDecision(...)` | PUT | `/api/prepay/claims/{id}/findings/{fid}/decision` | OPA | |
| `api.generateFindingsLetter(...)` | POST | `/api/prepay/claims/{id}/findings-letter` | OPA | |
| `api.exportDenialUrl(...)` | — | `{API_BASE_URL}/api/prepay/claims/{id}/export/denial` | OPA (correct path via helper) | URL helper only; actual fetch in component |
| `api.exportApprovalUrl(...)` | — | `{API_BASE_URL}/api/prepay/claims/{id}/export/approval` | OPA (correct path via helper) | URL helper only; actual fetch in component |
| `DenialPackageModal.tsx:42` | GET | `${API_BASE_URL}/claims/${id}/export/denial` | **BROKEN** | Missing `/api/prepay/` prefix — old backend path |
| `ApprovalExportModal.tsx:24` | GET | `${API_BASE_URL}/claims/${id}/export/approval` | **BROKEN** | Missing `/api/prepay/` prefix — old backend path |
| `api.documentFileUrl(id)` | — | `/api/documents/{id}/download` | OPA | |
| `api.documentViewUrl(id)` | — | `/api/documents/{id}/download?inline=1` | OPA | |
| `api.uploadDocument(...)` | POST | `/api/documents` | OPA | multipart; claim_id + kind=supporting |
| `api.deleteDocument(...)` | DELETE | `/api/documents/{id}` | OPA | |
| `api.listConfig()` | GET | `/api/runtime-config` | OPA | |
| `api.updateConfig(key, val)` | PATCH | `/api/runtime-config/{key}` | OPA | |
| `api.listEvidenceFindings(id)` | GET | `/api/prepay/claims/{id}/evidence-findings` | OPA | Code evidence scanner |
| `api.scanEvidence(id)` | POST | `/api/prepay/claims/{id}/scan-evidence` | OPA | |
| `api.dashboard()` | GET | `/api/prepay/dashboard` | OPA | |
| `api.myDashboard(period)` | GET | `/api/prepay/dashboard/me` | OPA | |
| `api.reportSummary()` | GET | `/api/prepay/reports/summary` | OPA | Type `ReportSummary` marked as stub |
| `api.reportSpecialist(uid)` | GET | `/api/prepay/reports/specialist/{uid}` | OPA | |
| `api.listIntake(params)` | GET | `/api/file-intake` | OPA | |
| `api.listUnmatched()` | GET | `/api/file-intake/unmatched` | OPA | |
| `api.uploadIntake(...)` | POST | `/api/file-intake/upload` | OPA | multipart; 90s timeout |
| `api.resolveIntake(...)` | POST | `/api/file-intake/{id}/resolve` | OPA | |
| `api.deleteIntake(id)` | DELETE | `/api/file-intake/{id}` | OPA | |
| `Members.tsx:75` | GET | `/api/members` | OPA | Direct `client.get` (not in api/index.ts) |
| `AssistantPanel.tsx:78` | POST | `/api/assistant/chat/stream` | OPA | SSE via `fetch` (bypasses axios interceptor; manually adds X-User-Id + Bearer) |
| `DemoGate.tsx:21,35` | GET/POST | `/api/auth/status`, `/api/auth/login` | OPA | |
| `authService.ts:37,52,89,120` | GET/POST | `/api/auth/me`, `/api/auth/login`, `/api/auth/logout`, `/api/auth/refresh` | OPA | Cookie-based auth flow (not currently wired into App.tsx mount) |

### OPA response shape → CG type adapters (`frontend/src/api/index.ts`)
- `OpaPrepayClaim` → `Claim`: renames `claim_id→id`, `claim_form_type→type`, `care_setting→claim_form`, `provider_name→provider`, `patient_name→patient`, `service_from_date→dos`, `claim_summary→summary`
- `OpaPrepayClaimDetail` extends above + maps `lines`, `ai_findings`, `documents`, `comments`, `audit_log`
- Role adapter: OPA `"analyst"` → CG `"specialist"` (`adaptUser`, `api/index.ts:~274`)

---

## 5. STATE & TYPES

### Core TS types (`frontend/src/api/types.ts`)

| Type | Key fields | Notes |
|---|---|---|
| `User` | `id: string` (UUID), `name`, `role: Role`, `initials`, `color_hex`, `specialty`, `supervisor_id`, `roles?`, `apps?`, `default_app?` | `roles[]`/`apps[]` from unified backend RBAC; used by NoAccessGate |
| `Role` | `"supervisor" \| "specialist" \| "analyst" \| "admin"` | `"analyst"` adapted to `"specialist"` at boundary |
| `Claim` | `id: string` (UUID), `icn`, `type: "CMS-1500"\|"UB-04"`, `claim_form`, `cpts: string[]`, `icd10: string[]`, `provider`, `patient`, `dos`, `billed_amount`, `status: ClaimStatus`, `priority: Priority`, `assigned_to: string\|null` (UUID) | IDs are UUID strings throughout |
| `ClaimDetail extends Claim` | `+lines: ClaimLine[]`, `+comments: Comment[]`, `+documents: Document[]`, `+audit_log: AuditLog[]`, `+ai_findings: AIFinding[]`, `+case_number`, `+case_status` | |
| `ClaimLine` | `id: string`, `line_number`, `cpt_code`, `units_billed`, `billed_amount`, `icd_codes: string[]` | |
| `AIFinding` | `id`, `claim_id`, `severity: "critical"\|"warning"\|"ok"`, `title`, `body`, `issue_summary?`, `suggestion?`, `detector_id?`, `fwa_indicator?`, `decision?: FindingDecision\|null` | |
| `Comment` | `id`, `claim_id`, `user_id`, `body`, `created_at` | Stored via `/api/prepay/claims/{id}/comments`; see UNPORTED note re: case_notes |
| `Document` | `id`, `claim_id?`, `filename`, `file_size_kb`, `kind: DocumentKind`, `uploaded_at` | `file_path` always `""` (OPA doesn't expose) |
| `ConfigEntry` | `key: string`, `value: string` | Backed by `/api/runtime-config` |
| `IntakeFile` | `intake_id: string`, `app: IntakeApp`, `category: IntakeCategory`, `status: IntakeStatus`, … | Unified intake model |
| `EvidenceFinding` | `finding_id`, `code_type: "icd10"\|"drg"`, `result: "found"\|"partial"\|"not_found"`, `confidence`, `evidence_text`, `document_id`, `page_number`, `additional_sources[]` | Code evidence scanner output |
| `PrepayDashboard` | `kpis[]`, `status_distribution[]`, `aging[]`, `decisions_trend[]`, `ai_coverage`, `specialty_mix[]`, `top_providers[]`, `workload[]` | |
| `ReportSummary` | `total_claims`, `approved_count/amount`, `denied_count/amount`, `avg_review_time_by_specialist`, `aging_buckets`, `dollar_by_specialty` | Marked as stub type; backend may not fully implement |
| `FindingDecision` | `status: "accepted"\|"rejected"`, `comment?`, `decided_by_user_id?`, `decided_at?` | |

**ID assumption**: All IDs are `string` (UUID) throughout `types.ts`. No `number` IDs remain in the type layer. The old `INTEGER` assumption is gone.

---

## 6. SCRIPTS

### `scripts/prewarm.sh`
- Purpose: pre-generate AI findings/summary/code-descriptions for all seeded claims before a demo
- **CRITICAL: Targets OLD standalone backend** — hardcoded `http://localhost:8002` default and uses OLD paths `/claims/{id}/analyze`, `/claims/{id}/summary`, `/claims/{id}/code-descriptions`
- Old claim IDs used: `CLM-2024-0001` through `CLM-2024-0010` (integer-style ICNs, OLD seed)
- Must be rewritten for OPA: base `http://localhost:8001`, paths `/api/prepay/claims/{id}/analyze`, `/api/prepay/claims/{id}/summary`, `/api/prepay/claims/{id}/code-descriptions`; IDs are now UUIDs (or ICNs from OPA seed)

### `scripts/build_overview_pptx.py`
- Purpose: generates `ClaimGuard_AI_Customer_Deck.pptx` from hardcoded content
- Requires `python-pptx` (not in any requirements.txt in this repo — run manually)
- No backend dependency; standalone pitch-deck generator

---

## 7. EXTERNAL INTEGRATIONS

| Integration | What | File:line | Env var / Config |
|---|---|---|---|
| OPA backend | All claim/user/config/intake API calls | `frontend/src/api/client.ts:8` | `appUrls.ts` hardcoded by build mode — no env var |
| OPA assistant (SSE) | `POST /api/assistant/chat/stream` | `AssistantPanel.tsx:78` | Same API_BASE_URL |
| Anthropic API | **NONE in frontend** — AI is called server-side by OPA. Frontend only renders findings/summaries returned by OPA. | N/A | N/A |
| pdfjs-dist | In-browser PDF rendering (PdfViewerModal, PdfHighlightViewer) | `components/claim-detail/Pdf*.tsx` | None |
| BroadcastChannel `opa_auth` | Cross-tab/cross-app auth event sync (login/logout/expire) | `services/authService.ts:169` | None |

---

## 8. MERGER GAP ANALYSIS

Status at time of map: Phase 2 is **substantially done** but 3 endpoint gaps + 2 broken component paths + 1 stale script remain.

### Gap 1 — BROKEN: Denial/Approval export ZIP paths (LIVE BUG)
| Item | File:line | Current (broken) path | Correct OPA path |
|---|---|---|---|
| Denial export | `DenialPackageModal.tsx:42` | `${API_BASE_URL}/claims/${id}/export/denial?...` | `${API_BASE_URL}/api/prepay/claims/${id}/export/denial?...` |
| Approval export | `ApprovalExportModal.tsx:24` | `${API_BASE_URL}/claims/${id}/export/approval?...` | `${API_BASE_URL}/api/prepay/claims/${id}/export/approval?...` |

Note: `api/index.ts` defines `exportDenialUrl()` / `exportApprovalUrl()` with the CORRECT OPA paths at `index.ts:483,487`. The modals bypass these helpers and construct the URL directly with the wrong path. Fix: replace hardcoded fetch URL with `api.exportDenialUrl(claim.id, currentUser.id)` / `api.exportApprovalUrl(claim.id, currentUser.id)`.

Note also: OPA CLAUDE.md lists denial/approval ZIP export as NOT ported to backend yet. So these endpoints may not exist on OPA at all — both the path fix AND the backend porting are required.

### Gap 2 — UNPORTED: Provider message endpoint
| Item | File:line | Path called | Status |
|---|---|---|---|
| `api.messageProvider()` | `api/index.ts:393` | POST `/api/prepay/claims/{id}/messages` | Backend NOT implemented on OPA (per CLAUDE.md deferred list) |
| `MessageProviderModal.tsx` | `claim-detail/MessageProviderModal.tsx:16` | Calls `api.messageProvider(...)` | Will fail with 404/405 at runtime |

### Gap 3 — UNPORTED: Evidence text search
| Item | File:line | Path called | Status |
|---|---|---|---|
| `api.searchEvidence()` | `api/index.ts:403` | GET `/api/prepay/claims/{id}/evidence?q=` | Backend NOT implemented on OPA (per CLAUDE.md deferred list). Distinct from `evidence-findings` (code scanner, which IS ported). |

### Gap 4 — STALE: prewarm.sh targets old backend
| Item | File:line | Problem |
|---|---|---|
| `scripts/prewarm.sh` | `scripts/prewarm.sh:1` | Targets `localhost:8002` (old CG backend), uses `/claims/{id}/...` paths, references integer-style CLM-2024-000N IDs |

### Gap 5 — COMMENTS vs CASE_NOTES
CLAUDE.md Phase-2 plan says: "comments flow → use case_notes (every reviewed claim gets a case first)". Current api/index.ts uses `POST /api/prepay/claims/{id}/comments` — verify this endpoint exists on OPA or adapt to the case_notes flow. The `Comment` type and `TabComments.tsx` component use the `comments[]` array on `ClaimDetail`; OPA backend would need to surface these via the prepay detail endpoint.

### Gap 6 — authService.ts not wired up
`services/authService.ts` implements a full cookie-based auth system (httpOnly cookies, auto-refresh, BroadcastChannel). It is imported nowhere in `App.tsx`, `main.tsx`, or `DemoGate.tsx`. The app uses the simpler HMAC Bearer token (`opa_demo_token` in localStorage) instead. `authService.ts` calls `/api/auth/me`, `/api/auth/refresh`, `/api/auth/logout` — whether these exist on OPA is unverified. Either wire it up properly or delete the dead code.

### Already-completed Phase-2 items (per opa/CLAUDE.md list)
| Item | Done | Evidence |
|---|---|---|
| API base re-point to OPA :8001 | YES | `appUrls.ts:24` |
| Switch IDs to UUID strings | YES | `types.ts` — all `id: string` |
| Adapt response shapes (provider_name→provider, patient_name→patient, etc.) | YES | `adaptClaim()`/`adaptClaimDetail()` in `api/index.ts` |
| cpts/icd10 from claim_lines aggregation | YES | Handled by OPA; `api/index.ts:lines` mapping |
| /config → /api/runtime-config | YES | `api/index.ts:listConfig/updateConfig` at `~568` |
| Document upload → /api/documents?claim_id= | YES | `api/index.ts:uploadDocument` → POST `/api/documents` with `claim_id` in body |
| comments → case_notes | PARTIAL | Endpoint is `/api/prepay/claims/{id}/comments`; whether OPA has this or needs case_notes path is unverified |

---

## 9. CONFIG & ENV

### Frontend env vars
| Var | Where used | Purpose |
|---|---|---|
| `VITE_ENVIRONMENT` | `EnvironmentBanner.tsx:5,7` | Shows non-prod banner when not `"production"` |
| `import.meta.env.PROD` | `appUrls.ts:32` | Vite built-in; switches DEV/PROD URL set |

**No `VITE_API_BASE_URL`** — URL is hardcoded in `appUrls.ts` by build mode. The `Layout.tsx:145` comment mentioning `VITE_API_BASE_URL` is stale/misleading.

### LocalStorage keys
| Key | Purpose |
|---|---|
| `claimguard.currentUserId` | UUID of selected user; sent as `X-User-Id` on every request |
| `opa_demo_token` | HMAC bearer token from OPA demo gate; sent as `Authorization: Bearer` |

### Hard-coded URL map (`appUrls.ts:14-30`)
| Mode | apiBase | claimguard | payguard | iam | siu | assistant |
|---|---|---|---|---|---|---|
| DEV | `http://localhost:8001` | `http://localhost:5175` | `http://localhost:5174` | `http://localhost:5177` | `http://localhost:5178` | `http://localhost:5179` |
| PROD | `https://payguard.penguinai.studio` | `https://claimguard.penguinai.studio` | `https://payguard.penguinai.studio` | `https://iam.penguinai.studio` | `https://siu.penguinai.studio` | `https://assistant.penguinai.studio` |

---

## 10. KNOWN ISSUES / GAPS / TODOs

1. **`DenialPackageModal.tsx:42` and `ApprovalExportModal.tsx:24`** — Wrong URL paths (missing `/api/prepay/` prefix). Both export buttons will return 404 in any environment. Fix: use `api.exportDenialUrl()` / `api.exportApprovalUrl()` helpers already in `api/index.ts:483,487`. ALSO: OPA backend has not yet ported these ZIP export endpoints (deferred per CLAUDE.md).

2. **`api.messageProvider` / `MessageProviderModal`** — Backend endpoint `/api/prepay/claims/{id}/messages` not implemented on OPA. UI shows the modal; clicking Send will get 404/422. Must either port to OPA backend or surface a "coming soon" error.

3. **`api.searchEvidence`** — Backend `/api/prepay/claims/{id}/evidence?q=` not implemented on OPA. Distinct from the code evidence scanner (`/evidence-findings`). Not currently called from any visible component (no search UI evident), so impact is low.

4. **`scripts/prewarm.sh`** — Entirely targets retired backend. Must be rewritten for OPA paths/IDs before use against the new stack.

5. **`services/authService.ts`** — Dead code (not imported anywhere in the app). Implements a more sophisticated cookie auth flow (httpOnly cookie + auto-refresh + BroadcastChannel). Either integrate with the app's lifecycle or delete to avoid confusion.

6. **Reports endpoints (`/api/prepay/reports/*`)** — `ReportSummary` type has a stub comment. Whether these are implemented on OPA is unverified from this map; test before relying on Reports page.

7. **`authService.ts` calls `/api/auth/me` and `/api/auth/refresh`** — OPA's auth routes are in `server/app/routes/` but whether `/api/auth/me` and `/api/auth/refresh` exist (vs just `/api/auth/login`) should be verified before wiring up `authService.ts`.

8. **`NoAccessGate` app check** — Requires `user.apps` to include `"claimguard"`. OPA users must be seeded with `apps=["claimguard", ...]` for the gate to pass. If a user has no `apps` array, the gate blocks the entire app.

9. **CLAUDE.md in claimguard root** — Describes the retired standalone backend (port 8002, `backend/main.py`, `backend/seed.py`). Misleading for any agent working in this repo. Should be updated or removed after Phase 3 backend deletion.

10. **`approval export fetch` doesn't set auth headers** — `ApprovalExportModal.tsx:24` uses raw `fetch()` without the `Authorization: Bearer` or `X-User-Id` headers that the axios interceptor sets. When the demo gate is enabled, this will 401. Same issue in `DenialPackageModal.tsx:42`.
