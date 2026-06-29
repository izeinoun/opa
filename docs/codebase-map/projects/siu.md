# SIU — Codebase Map (machine-readable)

> Generated 2026-06-29. Source root: `/Users/issamzeinoun/claude/siu`

---

## 1. IDENTITY

| Key | Value |
|-----|-------|
| **Path** | `/Users/issamzeinoun/claude/siu/frontend/` |
| **Purpose** | Special Investigations Unit workspace — manages FWA (Fraud/Waste/Abuse) escalations, investigations, law-enforcement referrals, and versioned JSON export packages. Surfaces both post-pay (PayGuard) and pre-pay (ClaimGuard) cases in read-only "frozen evidence" panels. No backend of its own — pure frontend that calls OPA's `/api/siu/*` endpoints. |
| **Stack** | React 18 + Vite 6 + TypeScript + Tailwind 3 + react-router-dom v6 + TanStack Query v5 + axios + pdfjs-dist + react-markdown + DOMPurify |
| **Entrypoint** | `src/main.tsx:1` → `<DemoGate>` → `<App>` → `<Routes>` |
| **Dev port** | `:5178` (strictPort) — `vite.config.ts:7`, `package.json:7` |
| **Prod host** | `https://siu.penguinai.studio` — `src/config/appUrls.ts:18` |
| **Run scripts** | `npm run dev` (`:5178`), `npm run build`, `npm run preview`, `npm start` (serves `dist/`) |

---

## 2. STRUCTURE

```
frontend/
├── src/
│   ├── main.tsx              — React root; wraps in DemoGate + QueryClient + BrowserRouter
│   ├── App.tsx               — Route definitions (4 real + 2 legacy redirects)
│   ├── DemoGate.tsx          — Shared-login gate; polls /api/auth/status; stores opa_demo_token
│   ├── index.css             — Tailwind base
│   ├── vite-env.d.ts
│   ├── api/
│   │   ├── client.ts         — axios instance (baseURL from appUrls), X-User-Id + Bearer interceptors
│   │   ├── index.ts          — All API calls (every OPA SIU endpoint + /api/users + /api/documents)
│   │   └── types.ts          — All TypeScript types mirroring siu_schemas.py + case_schemas.py
│   ├── config/
│   │   └── appUrls.ts        — Hardcoded URL config; switches DEV/PROD by import.meta.env.PROD (no env vars needed)
│   ├── pages/
│   │   ├── DashboardPage.tsx            — SIU team metrics + FWA rule breakdown
│   │   ├── QueuePage.tsx                — Investigation queue (shared, parameterised by pipelineMode)
│   │   ├── InvestigationDetailPage.tsx  — Scaffold: header, action bar, notes, referrals, exports
│   │   ├── PostPayInvestigationDetailPage.tsx — Wrapper: passes PostPayCasePanel as renderer
│   │   └── PrePayInvestigationDetailPage.tsx  — Wrapper: passes PrePayCasePanel as renderer
│   ├── components/
│   │   ├── SiuLayout.tsx          — Sidebar + top bar + AssistantPanel slot
│   │   ├── ActorPicker.tsx        — Demo user-switcher; writes siu.currentUserId to localStorage
│   │   ├── AppSwitcher.tsx        — Links to IAM / PayGuard / ClaimGuard (not Assistant — that's in-app)
│   │   ├── AssistantPanel.tsx     — SSE chat panel → POST /api/assistant/chat/stream
│   │   ├── PostPayCasePanel.tsx   — Lazy-load PayGuard CaseDetail for a linked case (read-only)
│   │   ├── PrePayCasePanel.tsx    — Lazy-load ClaimGuard PrepayDetail + evidence (read-only)
│   │   ├── PdfHighlightViewer.tsx — pdf.js canvas viewer with evidence-text highlight overlay
│   │   ├── NoAccessGate.tsx       — Checks user.apps from /api/users; blocks non-siu users
│   │   └── EnvironmentBanner.tsx  — Green (dev) / Red (prod) banner
│   └── services/
│       └── authService.ts         — Cookie-based auth util (BroadcastChannel cross-app sync).
│                                    NOTE: NOT imported by main.tsx / App.tsx — effectively dead
│                                    code in the current wiring. DemoGate handles auth instead.
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── tsconfig.json
├── .env.example               — Documents VITE_* vars; NOT actually read (URLs hardcoded in appUrls.ts)
└── railway.json
```

---

## 3. PAGES / ROUTES

| Route | Component | File:line | Purpose |
|-------|-----------|-----------|---------|
| `/` | `<Navigate to="/dashboard">` | `App.tsx:18` | Default redirect |
| `/dashboard` | `DashboardPage` | `pages/DashboardPage.tsx:75` | SIU KPIs, status/type/pipeline distributions, weekly volume, investigator workload, FWA rule breakdown |
| `/post-pay` | `QueuePage pipelineMode="post_pay"` | `pages/QueuePage.tsx:60` | Post-pay investigation queue (Active/Closed toggle, My/All scope) |
| `/post-pay/investigations/:id` | `PostPayInvestigationDetailPage` | `pages/PostPayInvestigationDetailPage.tsx:12` | Investigation scaffold + PayGuard-style case panels |
| `/pre-pay` | `QueuePage pipelineMode="pre_pay"` | `pages/QueuePage.tsx:60` | Pre-pay investigation queue |
| `/pre-pay/investigations/:id` | `PrePayInvestigationDetailPage` | `pages/PrePayInvestigationDetailPage.tsx:12` | Investigation scaffold + ClaimGuard-style case panels |
| `/closed` | `<Navigate to="/post-pay">` | `App.tsx:35` | Legacy redirect |
| `/investigations/:id` | `<Navigate to="/post-pay">` | `App.tsx:37` | Legacy redirect (loses id) |

### InvestigationDetailPage sub-sections (shared scaffold)
- **Header** (`InvestigationDetailPage.tsx:211`) — type, status, escalation, outcome, frozen-evidence banner
- **ActionBar** (`InvestigationDetailPage.tsx:321`) — Open / Close investigation buttons; CloseModal
- **Linked cases** (`InvestigationDetailPage.tsx:133`) — delegates to `renderLinkedCases` prop or compact fallback
- **NotesSection** (`InvestigationDetailPage.tsx:449`) — immutable note add form + list; supports confidential flag
- **ReferralsSection** (`InvestigationDetailPage.tsx:554`) — FileReferralModal + RecordOutcomeModal
- **ExportsSection** (`InvestigationDetailPage.tsx:850`) — versioned JSON export generation + download

---

## 4. API LAYER

### Backend base URL
- **Source**: `src/config/appUrls.ts:35` → `export const API_BASE_URL = CFG.apiBase`
- **Dev**: `http://localhost:8001` (`appUrls.ts:24`)
- **Prod**: `https://payguard.penguinai.studio` (`appUrls.ts:15`)
- **Set on axios instance**: `src/api/client.ts:7` → `baseURL: API_BASE_URL`
- **Confirmed**: targets OPA backend `:8001`, NOT a separate SIU backend.

### Request headers (via interceptors — `client.ts:15-22`)
- `X-User-Id`: from `localStorage.siu.currentUserId`
- `Authorization: Bearer <token>`: from `localStorage.opa_demo_token`

### All endpoints called (`src/api/index.ts`)

| Method | Path | Function | Line | Maps to OPA route |
|--------|------|----------|------|--------------------|
| GET | `/api/users` | `listUsers` | 23 | `server/app/routes/users.py` |
| GET | `/api/siu/queue` | `listQueue` | 33 | `siu.py:49` `list_siu_queue` |
| GET | `/api/siu/investigations/:id` | `getInvestigation` | 42 | `siu.py:64` `get_investigation` |
| GET | `/api/siu/cases/:id/prepay-detail` | `getPrepayCaseDetail` | 51 | `siu.py:111` `get_prepay_case_detail` |
| GET | `/api/siu/cases/:id/postpay-detail` | `getPostpayCaseDetail` | 61 | `siu.py:151` `get_postpay_case_detail` |
| GET | `/api/siu/dashboard` | `getDashboard` | 68 | **NOT IN siu.py — MISSING endpoint** |
| GET | `/api/documents/:id/download` | `documentFileUrl` | 75 | `routes/file_intake.py` or `routes/documents.py` |
| POST | `/api/siu/escalate` | `escalateCase` | 80 | `siu.py:188` `escalate_case` |
| POST | `/api/siu/investigations/:id/open` | `openInvestigation` | 93 | `siu.py:199` `open_investigation` |
| POST | `/api/siu/investigations/:id/cases` | `addCaseToInvestigation` | 106 | `siu.py:213` `add_case_to_investigation` |
| POST | `/api/siu/investigations/:id/notes` | `addNote` | 120 | `siu.py:232` `add_note` |
| PATCH | `/api/siu/investigations/:id/status` | `updateStatus` | 134 | `siu.py:255` `update_status` |
| POST | `/api/siu/investigations/:id/referrals` | `fileReferral` | 147 | `siu.py:271` `file_referral` |
| PATCH | `/api/siu/investigations/:id/referrals/:rid` | `recordReferralOutcome` | 164 | `siu.py:287` `record_referral_outcome` |
| POST | `/api/siu/investigations/:id/close` | `closeInvestigation` | 183 | `siu.py:309` `close_investigation` |
| POST | `/api/siu/investigations/:id/exports` | `generateExport` | 196 | `siu.py:322` `generate_export` |
| GET | `/api/siu/investigations/:id/exports/:pkg/download` | `exportDownloadUrl` | 207 | `siu.py:340` `download_export` |
| POST | `/api/assistant/chat/stream` | (fetch in `AssistantPanel.tsx:78`) | `AssistantPanel.tsx:78` | `routes/assistant.py` (SSE) |
| GET | `/api/auth/status` | (fetch in `DemoGate.tsx:21`) | `DemoGate.tsx:21` | `routes/auth.py` |
| POST | `/api/auth/login` | (fetch in `DemoGate.tsx:35`) | `DemoGate.tsx:35` | `routes/auth.py` |

---

## 5. DATA SHAPES

All types in `src/api/types.ts`.

| Type | Line | Description |
|------|------|-------------|
| `User` | `types.ts:4` | OPA user (id, name, role, roles[], apps[], initials, color_hex, specialty) |
| `Investigation` | `types.ts:112` | Full investigation: type, status, outcome, escalation_source/reason, notes[], referrals[], exports[], cases[CaseSummaryForSIU] |
| `SIUQueueRow` | `types.ts:139` | Queue list item: pipeline_mode, case_count, provider_org_names[], detector_ids[], total_at_risk |
| `CaseSummaryForSIU` | `types.ts:53` | Nested in Investigation.cases: case_id, case_number, claim_id, icn, pipeline_mode, siu_frozen, law_enforcement_hold, detector_ids[] |
| `InvestigationNote` | `types.ts:70` | note_id, note_type, body, is_confidential, author_user_id, author_name |
| `LawEnforcementReferral` | `types.ts:82` | referral_id, agency_name, referral_type, referral_summary, referral_outcome, outcome_notes |
| `SIUExportPackage` | `types.ts:98` | package_id, version, integrity_hash, delivery_status, delivery_destination |
| `PostPayCaseDetailForSIU` | `types.ts:367` | PayGuard CaseDetail: case_id, claim(PostPayClaimForSIU), detector_results[], notes[], audit_logs[] |
| `PostPayClaimForSIU` | `types.ts:313` | claim_number, lob, member(PostPayMember), rendering_provider, lines(PostPayClaimLine[]) |
| `PostPayClaimLine` | `types.ts:300` | line_number, cpt_code, icd_codes[], billed_amount, paid_amount, at_risk_amount, at_risk_detector_id |
| `PostPayFinding` | `types.ts:329` | detector_code, overpayment_amount, confidence_score, fwa_indicator, fwa_rule_code |
| `PrepayCaseDetailForSIU` | `types.ts:254` | claim_detail(PrepayClaimDetailForSIU) + evidence(EvidenceFindingsResponse) |
| `PrepayClaimDetailForSIU` | `types.ts:189` | cpts[], icd10[], ai_findings[], documents[], comments[], summary, code_descriptions |
| `PrepayAIFinding` | `types.ts:159` | severity('critical'/'warning'/'ok'), title, body, fwa_indicator, fwa_rule_code |
| `EvidenceFinding` | `types.ts:228` | code_type('icd10'/'drg'), code, result('found'/'partial'/'not_found'), evidence_text, document_id, page_number |
| `SIUDashboard` | `types.ts:386` | kpis[], status_distribution[], type_distribution[], pipeline_distribution[], weekly_volumes[], outcomes_breakdown[], investigator_workload[], fwa_rule_breakdown[] |
| `InvestigationStatus` | `types.ts:19` | Union: OPEN / PENDING_EXTERNAL_INFO / PENDING_LAW_ENFORCEMENT / REFERRAL_SUBMITTED / CLOSED |
| `InvestigationType` | `types.ts:24` | Union: TIME_VOLUME_ANOMALY / SUBROGATION / EXCLUDED_PROVIDER / FRAUD_PATTERN / OTHER |
| `InvestigationOutcome` | `types.ts:31` | Union: FRAUD_CONFIRMED / NO_FRAUD_FOUND / INSUFFICIENT_EVIDENCE / SUBROGATION_RECOVERY_INITIATED / CASE_CLOSED_NO_ACTION |
| `EscalationSource` | `types.ts:40` | Union: analyst_referral / dce_13 / dce_15 / pattern_threshold |
| `PipelineMode` | `types.ts:137` | Union: 'post_pay' / 'pre_pay' / 'mixed' |

---

## 6. EXTERNAL INTEGRATIONS

| Target | Where | Env / Config | Notes |
|--------|-------|--------------|-------|
| OPA backend `:8001` / `payguard.penguinai.studio` | `config/appUrls.ts:15,24` | Hardcoded, no env var needed | **Primary**: ALL data API calls go here |
| `POST /api/assistant/chat/stream` | `components/AssistantPanel.tsx:78` | Same `API_BASE_URL` | SSE stream; uses `fetch` not axios (bypasses interceptor, manually adds headers) |
| `iam.penguinai.studio` / `:5177` | `config/appUrls.ts:16,25` | Hardcoded | Cross-app link only (AppSwitcher + NoAccessGate IAM link). No API calls. |
| `payguard.penguinai.studio` / `:5174` | `config/appUrls.ts:17,26` | Hardcoded | Cross-app link only |
| `claimguard.penguinai.studio` / `:5175` | `config/appUrls.ts:18,27` | Hardcoded | Cross-app link only |
| `assistant.penguinai.studio` / `:5179` | `config/appUrls.ts:19,28` | Hardcoded | URL defined but NOT used in AppSwitcher (Assistant is in-app panel, not cross-app nav) |

**Confirmed: SIU does NOT have its own backend.** All data comes from OPA's unified backend.

---

## 7. CONFIG & ENV

### Runtime configuration
**No env vars are required or read at runtime.** URLs are committed in `src/config/appUrls.ts` and switch automatically by `import.meta.env.PROD` (Vite build mode). See `appUrls.ts:12-13` for the rationale.

### `.env.example` (`frontend/.env.example`)
Documents vars that are NOT actually read by the codebase (appUrls.ts does not read `VITE_*`). The example file is stale / aspirational documentation.

| Var | Default | Status |
|-----|---------|--------|
| `VITE_API_BASE_URL` | `http://localhost:8001` | **NOT READ** — URL from appUrls.ts |
| `VITE_IAM_URL` | `http://localhost:5177` | **NOT READ** |
| `VITE_PAYGUARD_URL` | `http://localhost:5174` | **NOT READ** |
| `VITE_CLAIMGUARD_URL` | `http://localhost:5175` | **NOT READ** |
| `VITE_SIU_URL` | `http://localhost:5178` | **NOT READ** |
| `VITE_ENVIRONMENT` | (unset) | READ by `EnvironmentBanner.tsx:7` only; optional |

### localStorage keys
| Key | Written by | Read by | Purpose |
|-----|-----------|---------|---------|
| `siu.currentUserId` | `ActorPicker.tsx:79`, `NoAccessGate.tsx:48` | `client.ts:16`, `QueuePage.tsx:65`, `AssistantPanel.tsx:85` | Active persona → `X-User-Id` header |
| `opa_demo_token` | `DemoGate.tsx:36` | `client.ts:19`, `AssistantPanel.tsx:86` | Demo gate JWT → `Authorization: Bearer` |

### React Query defaults (`main.tsx:9-12`)
- `staleTime: 30_000` (30 s)
- `retry: false`

### railway.json
Exists at `frontend/railway.json` — no content surfaced in this scan (build/deploy config).

---

## 8. KNOWN ISSUES / GAPS / TODOs

### Critical
1. **`GET /api/siu/dashboard` is MISSING in OPA backend** (`api/index.ts:68` calls it; `server/app/routes/siu.py` has no `/dashboard` route). `DashboardPage.tsx:76` will always 404/error in any deployment. The `SIUDashboard` type shape (`types.ts:386`) is fully defined but the server endpoint must be implemented.

### Auth / Identity
2. **`authService.ts` is dead code**. It defines a full cookie-based auth system with BroadcastChannel cross-app sync (`services/authService.ts:1`), but is NOT imported anywhere in `main.tsx`, `App.tsx`, or any component. Auth is handled entirely by `DemoGate.tsx` (token in localStorage) + `NoAccessGate.tsx` (apps check).
3. **No real auth** — `X-User-Id` is trusted from localStorage; anyone can impersonate any user. Standard OPA demo-mode caveat (`CLAUDE.md`).

### Data / API
4. **Legacy redirect loses `:id`** — `App.tsx:37-39` redirects `/investigations/:id` to `/post-pay` (not `/post-pay/investigations/:id`). Bookmarked investigation links from before the pipeline split silently drop the user on the queue instead of the detail.
5. **Queue polling is double-counted** — `SiuLayout.tsx:48-57` fires two separate `listQueue` calls (one per pipeline) on every mount for sidebar badge counts. These are independent from the queue page's own query keyed differently (`siu-queue-count` vs `siu-queue`), so toggling pipelines causes 3 in-flight calls.

### Components
6. **`PdfHighlightViewer` adapted from ClaimGuard** (`PdfHighlightViewer.tsx:1` comment) — stopwords list and highlight logic are duplicated verbatim from `claimguard/frontend`. No shared package.
7. **`AssistantPanel` adapted from PayGuard** (`AssistantPanel.tsx:2` comment) — SSE parsing + `ask_user` flow duplicated across apps.
8. **`ActorPicker` auto-selects siu_investigator role** (`ActorPicker.tsx:55`) — any user without that role but with `apps: ['siu']` won't be auto-selected; they'll see "Loading…" until they pick manually.

### Config
9. **`.env.example` is misleading** — documents `VITE_*` vars that `appUrls.ts` never reads. A developer following the example and setting env vars will see no effect.
10. **`NoAccessGate` `appName="siu"`** (`App.tsx:14`) checks `user.apps.includes('siu')`; the OPA backend must populate `apps` on the user record for SIU users or the gate will block everyone.
