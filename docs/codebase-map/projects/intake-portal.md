# intake-portal — Machine-Readable Codebase Map

> Generated 2026-06-29. Source of truth: code beats README where they conflict.

---

## 1. IDENTITY

| Field | Value |
|---|---|
| **Disk path** | `/Users/issamzeinoun/claude/intake-portal` |
| **Purpose** | Standalone "Secure File Intake Portal" — browser-based secure drop-folder for payer IT/Data teams to push files (X12 835/837, medical records, claim PDFs) into the unified OPA backend for automated processing |
| **Who uses it** | Payer IT/Data operators (`intake`-role users, not providers, not members) |
| **Stack** | React 19 + TypeScript 6 + Vite 8 + Tailwind 3 + Axios 1; no router, no state library |
| **Entrypoint** | `index.html` → `src/main.tsx:6` → `<App />` in `src/App.tsx:518` |
| **Dev port** | `5181` (`vite.config.ts:10`) — **README says 5180; vite.config.ts wins** |
| **Run scripts** | `npm run dev` (vite, :5181) / `npm run build` (tsc -b && vite build) / `npm run start` (serve dist, `PORT` env or 3000) |
| **Railway deploy** | `railway.toml`: builder=nixpacks, buildCommand=`npm run build`, startCommand=`npm run start`, restart=on_failure (max 10) |
| **Suite ports** | payguard:5174, claimguard:5175, siu:5178, **intake:5181** (5180 in README — stale) |

---

## 2. STRUCTURE

```
intake-portal/
├── index.html                 HTML shell; mounts #root; loads src/main.tsx
├── vite.config.ts             Vite config; port 5181; no proxy (all API calls go to explicit base URL)
├── tsconfig.json              strict, ES2022, noEmit, bundler resolution
├── tailwind.config.js         standard; content: index.html + src/**/*.{ts,tsx}
├── postcss.config.js          autoprefixer
├── package.json               deps: axios, lucide-react, react, react-dom, serve
├── railway.toml               deploy config (see §1)
├── public/                    favicon.svg (only static asset)
└── src/
    ├── main.tsx               React 19 createRoot; StrictMode wrapper
    ├── index.css              Tailwind directives + body/html height reset
    ├── vite-env.d.ts          VITE env type shim
    ├── config/
    │   └── appUrls.ts         Backend base URL resolution (env/prod/dev); payguard deep-link helper
    └── App.tsx                Entire UI — login screen, folder grid, intake drawer, recent-transfers table
```

**No separate `components/`, `pages/`, `hooks/`, `services/` directories.** All logic lives in `src/App.tsx` (676 lines) plus `src/api.ts`.

---

## 3. PAGES / COMPONENTS

All UI is a single SPA in `App.tsx`. No React Router. Phase state machine drives screen transitions.

### Phase state machine (`App.tsx:519`)
| Phase | Screen rendered |
|---|---|
| `checking` | Full-screen loading spinner |
| `locked` | `<LoginScreen>` — demo gate password form |
| `ready` | Main portal layout (header + folder grid + recent-transfers table) |
| `error` | Full-screen error message (intake service unavailable) |

### `<LoginScreen>` (`App.tsx:482`)
- Password form → `POST /api/auth/login` → stores Bearer token in localStorage
- On success: phase → `checking` → `bootstrap()`

### `<App>` main layout (phase=ready) (`App.tsx:581`)
- **Header**: teal gradient; "Secure File Intake Portal"; "Signed in as {operator.name}"
- **Folder groups** (`GROUPS` constant, `App.tsx:25`):
  - "Remittance & Claims (PayGuard)": 835 ERA (`.x12,.835,.edi,.txt`), 837 Claim, Medical Records (`.pdf`)
  - "Pre-pay Claims (ClaimGuard)": Claim Forms / CMS-1500 / UB-04 (`.pdf`)
- **Recent Transfers table**: filename, category, member name/number, status pill, outcome message; manual refresh button
- Clicking a folder card → opens `<IntakeDrawer>` as a slide-in panel

### `<FolderCard>` (`App.tsx:74`)
- Dashed-border tile; icon + label + hint + "Click to begin upload"
- onClick → `setActiveSpec(spec)` → opens drawer

### `<IntakeDrawer>` (`App.tsx:118`)
Two-step slide-in panel (right side, 480px max):
- **Step 1 — Info collection** (`App.tsx:261`): patient fields (memberNumber, firstName, lastName, dob, dos, providerName) OR remittance fields (payerName, payerId, remitDate, totalPaid). Save = simulated `setTimeout(1300ms)` only; generates local `REF-{date}-{rand}` token. **No backend call in Step 1.**
- **Step 2 — File upload** (`App.tsx:372`): drag-and-drop zone + file input; calls `uploadIntake()` → `POST /api/file-intake/upload` multipart; progress bar via `onUploadProgress`; success auto-closes after 1600ms; errors surface backend `detail` string

### `<StatusPill>` (`App.tsx:53`)
Badge component mapping `IntakeStatus` → label + color + icon: pending (spinner), case_created (emerald), linked (sky), unmatched (amber), rejected/error (rose).

---

## 4. API LAYER

### Base URL resolution (`src/config/appUrls.ts:1`)

```
DEV  (import.meta.env.DEV)  → http://localhost:8001
PROD (import.meta.env.PROD) → https://payguard.penguinai.studio
```

Override at **build time** (baked into bundle):
- `VITE_API_BASE_URL` → overrides `apiBase` (`appUrls.ts:21`)
- `VITE_PAYGUARD_URL` → overrides payguard deep-link base (`appUrls.ts:22`)

Exported: `API_BASE_URL` (string, no trailing slash, no `/api`) + `payguardUrl(path)` helper.

### Axios client (`src/api.ts:16`)
- `baseURL = API_BASE_URL`
- Request interceptor: attaches `X-User-Id: {currentUserId}` + `Authorization: Bearer {token}` from localStorage (`api.ts:21`)
- Response interceptor: clears `opa_demo_token` on 401 (except `/auth/login`) to force re-login (`api.ts:31`)

### Endpoints called

| Method | Path | File:Line | Request | Response |
|---|---|---|---|---|
| `GET` | `/api/auth/status` | `api.ts:83` | — | `{ gate_enabled: boolean }` |
| `POST` | `/api/auth/login` | `api.ts:88` | `{ password }` JSON | `{ token: string }` |
| `GET` | `/api/users` | `api.ts:96` | — | `PortalUser[]`; finds `role==='intake'` user |
| `POST` | `/api/file-intake/upload` | `api.ts:118` | `multipart/form-data` — fields: `file`, `app` (payguard\|claimguard), `category` (835\|837\|medical\|claim_pdf`); timeout 90s | `IntakeFile` (see §4 types) |
| `GET` | `/api/file-intake` | `api.ts:128` | — | `IntakeFile[]` |

**Does NOT call `/api/prepay/claims/from-pdf`.** ClaimGuard claim PDFs are ingested via `/api/file-intake/upload?category=claim_pdf` — the backend's `_process_claim_pdf` handler internally delegates to `prepay_intake_service.ingest_extracted_claim` (`server/app/routes/file_intake.py:297`).

### `IntakeFile` shape (`api.ts:49`)
```typescript
{
  intake_id: string         // UUID
  app: 'payguard' | 'claimguard'
  category: '835' | '837' | 'medical' | 'claim_pdf'
  filename: string
  file_size_kb: number
  uploaded_at: string
  uploaded_by_user_id: string | null
  extraction_status: string | null
  extracted_member_number: string | null
  extracted_member_name: string | null
  extracted_dob: string | null
  extracted_service_dates: string[]
  status: 'pending' | 'case_created' | 'linked' | 'unmatched' | 'rejected' | 'error'
  candidate_case_ids: string[]
  message: string | null
  result_case_id: string | null
  result_claim_id: string | null
  result_document_id: string | null
  result_case_number: string | null
  created_at: string
  updated_at: string
}
```

### Backend route behavior summary (`server/app/routes/file_intake.py`)
| category | Backend processing |
|---|---|
| `835` | `_process_835` → `create_case_from_835` → `status=case_created` (or `unmatched` if no CLP) |
| `837` | `_process_837` → `parse_837` → `match_to_case` → optionally `enrich_claim_from_837` → `status=linked\|unmatched` |
| `medical` | `_process_medical` → `extract_pdf_text` → `ai_service.extract_patient_identifiers` → `match_to_case` → `status=linked\|unmatched` |
| `claim_pdf` | `_process_claim_pdf` → `extract_pdf_text` → `ai_service.extract_claim_from_text` → `ingest_extracted_claim` → `status=case_created` |

Auth guard on all file-intake routes: `require_role("admin", "intake")` (`file_intake.py:65`).

---

## 5. EXTERNAL INTEGRATIONS

| Target | Used for | Source | Env var |
|---|---|---|---|
| `http://localhost:8001` (dev) | All API calls | `src/config/appUrls.ts:14` | overridable via `VITE_API_BASE_URL` |
| `https://payguard.penguinai.studio` (prod) | API base + PayGuard deep-links | `src/config/appUrls.ts:9` | overridable via `VITE_API_BASE_URL`, `VITE_PAYGUARD_URL` |

No direct third-party calls. No WebSocket. No CDN asset loads.

---

## 6. CONFIG & ENV

### Vite env vars (build-time baked)
| Var | Default (dev) | Default (prod) | Purpose |
|---|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8001` | `https://payguard.penguinai.studio` | Backend API root |
| `VITE_PAYGUARD_URL` | `http://localhost:5174` | `https://payguard.penguinai.studio` | PayGuard deep-link base |

### Runtime env (Railway / serve)
| Var | Purpose |
|---|---|
| `PORT` | `npm run start` listen port; defaults to 3000 if unset (`package.json:12`) |

### localStorage keys (`api.ts:4–5`)
| Key | Value |
|---|---|
| `opa_demo_token` | HMAC Bearer token from OPA demo gate |
| `intake.currentUserId` | UUID of the resolved intake-role user |

### No `.env` file in repo. No `dotenv`. Env only matters at `vite build` time for `VITE_*` vars.

---

## 7. KNOWN ISSUES / GAPS / TODOs

1. **Port mismatch**: `README.md:30` documents dev port as `5180`; `vite.config.ts:10` sets `5181`. README is stale.

2. **Step 1 form data is never sent to backend**: Patient/remittance metadata collected in Step 1 (`App.tsx:164`, `handleSave`) is only simulated (1300ms timeout, local ref token generated). The fields (memberNumber, dob, dos, providerName, payerName, etc.) are **not attached to the multipart upload**. Backend extracts member identity from the file content itself (via EDI parse or LLM). Step 1 is UX scaffolding only — a cosmetic gate.

3. **No unmatched queue UI**: Backend exposes `GET /api/file-intake/unmatched` and `POST /api/file-intake/{id}/resolve` but the portal has no screen for resolving unmatched files. Users see `status=unmatched` in the table but cannot act on it from this UI (must use PayGuard analyst app).

4. **No download/preview**: Backend exposes `GET /api/file-intake/{intake_id}/download` and `GET /api/file-intake/outputs` + `GET /api/file-intake/outputs/{id}/download` but the portal never calls them. Recent-transfers table is read-only.

5. **No delete UI**: `DELETE /api/file-intake/{intake_id}` exists on backend; not wired in portal.

6. **No app/category filter on list**: `GET /api/file-intake` supports `?app=&category=&status=` query params; `listIntake()` (`api.ts:128`) calls with no params — always fetches all categories for all apps.

7. **No polling / live status**: The `pending` status means processing is ongoing, but the portal only refreshes on explicit button click (`App.tsx:629`). No auto-poll for pending rows.

8. **Prod URL points to payguard subdomain**: `PROD.apiBase` = `https://payguard.penguinai.studio` shares host with the PayGuard frontend. If that domain serves both the static React app and the FastAPI backend via Railway, there is no separation; if not, CORS or routing needs to be verified on Railway deployment.

9. **intake-role user must exist in OPA DB**: `resolveIntakeUser()` (`api.ts:96`) fails silently (returns null → `phase=error`) if no `role==='intake'` user is seeded. `make seed` must have run on the connected backend.

10. **No TypeScript path aliases**: all imports are relative; `src/api.ts` and `src/config/appUrls.ts` are referenced directly.

---

## CROSS-REFERENCE: Intake logic overlap

| Component | Route used | Backend service | Overlap with intake-portal? |
|---|---|---|---|
| **intake-portal** | `POST /api/file-intake/upload` | `routes/file_intake.py` | **This app** |
| **OPA PayGuard frontend** (embedded) | same `/api/file-intake/*` | same | Same endpoints; UI embedded inside PayGuard `AdminPage` — not a standalone app |
| **`/api/prepay/claims/from-pdf`** | `routes/prepay.py` | `prepay_intake_service.py` | Different route — direct ClaimGuard PDF intake without `intake_files` record; not used by intake-portal |
| **`ProviderPortalUploadButton.tsx`** | `POST /api/provider-portal/upload-recoup-notice` | `provider_portal_service.py` | Outbound (push recoup notice OUT to provider portal); unrelated to file intake IN |
| **ClearLink** | N/A | N/A | ClearLink has its own route prefix (`/api/clearlink/*`); does not share this flow |
