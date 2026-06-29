# mock-provider-portal — Machine-Readable Codebase Map

---

## 1. IDENTITY

| Field | Value |
|---|---|
| **Absolute path** | `/Users/issamzeinoun/claude/overcoding/mock-provider-portal/` |
| **Purpose** | Simulate a payer-side provider web portal that accepts recoup-notice PDF uploads via browser form; lets OPA's Playwright automation verify the full upload end-to-end without hitting a real portal |
| **Stack** | Node.js 18, Express 4.18, express-session, multer 1.4.5-lts |
| **Entrypoint** | `server.js:1` |
| **Port** | `3002` (hardcoded `server.js:8`) |
| **Run scripts** | `package.json:7` `"start": "node server.js"`, `package.json:8` `"dev": "nodemon server.js"` |
| **Docker** | `Dockerfile` — `FROM node:18-alpine`, `EXPOSE 3002`, `CMD ["npm","start"]`; HEALTHCHECK pings `/api/status` every 30 s |
| **Dev deps** | `@playwright/test ^1.61.1`, `playwright ^1.61.1`, `nodemon ^3.0.1` |

---

## 2. ENDPOINTS

All routes defined in `server.js`.

| Method | Path | Line | Auth required | Purpose |
|---|---|---|---|---|
| GET | `/login` | 72 | No | Render HTML login form; shows "provider / password" demo hint |
| POST | `/login` | 258 | No | Validate `username`/`password` against hardcoded `VALID_USERNAME='provider'` / `VALID_PASSWORD='password'`; sets `req.session.authenticated=true`, `req.session.providerId='PROV-001'`; redirects to `/dashboard` or `/login?error=1` |
| GET | `/dashboard` | 270 | `requireAuth` (session) | Full HTML dashboard: provider info, static stats, member-info form, file upload form (`POST /upload`), table of previously uploaded files from `uploads/` dir |
| POST | `/upload` | 750 | `requireAuth` | multer `upload.single('notice')` — saves file to `uploads/` as `{timestamp}-{originalname}`; renders upload-confirmed HTML page with 8-second auto-redirect to `/dashboard` |
| GET | `/denial-letter` | 1023 | `requireAuth` | HTML page with claim-info form and a separate file upload form (`POST /upload-denial`) — captures Claim ID, Member ID, DOS, denial code, billed/denied amounts, CPT, ICD-10, denial notes |
| POST | `/upload-denial` | 1259 | `requireAuth` | multer `upload.single('denial')` — saves denial letter file to `uploads/`; renders simple success HTML page |
| GET | `/downloads/:filename` | 1285 | `requireAuth` | `res.download(filepath)` — serves any file from `uploads/` dir by name |
| GET | `/logout` | 1291 | No | `req.session.destroy()` → redirect `/login` |
| GET | `/api/status` | 1297 | No | JSON `{status:'ok', uploadCount:N, files:[...]}` — reads `uploads/` dir; no session check; used by Docker HEALTHCHECK and automation polling |

---

## 3. PLAYWRIGHT AUTOMATION

File: `playwright-upload.js`

**Purpose:** Automate the full browser flow to upload a recoup-notice PDF to this portal (or any compatible portal URL). Called by OPA's `ProviderPortalService` as a subprocess (or standalone for local testing).

**Chromium launch:** `playwright-upload.js:52` — `chromium.launch({ headless: false })` (NOTE: `headless: false` is the script default; OPA's service passes `--headless` as an arg when calling it in production).

**CLI args parsed at:** `playwright-upload.js:26-31` — `--key=value` style.

| Arg | Default | Line |
|---|---|---|
| `--portal-url` | `http://localhost:3002` | 33 |
| `--file` | (required) | 34 |
| `--username` | `provider` | 35 |
| `--password` | `password` | 36 |
| `--member-first` | `John` | 37 |
| `--member-last` | `Doe` | 38 |
| `--member-id` | `MBR-00123456` | 39 |
| `--claim-id` | `ERA-2024-78901` | 40 |
| `--provider` | `Capitol Spine & Rehab` | 41 |

**Automation steps (function `uploadRecoupNotice`, line 45):**

1. `playwright-upload.js:59-74` — Navigate to `{PORTAL_URL}/login`, fill `input[name="username"]` + `input[name="password"]`, click submit, await redirect to `/dashboard`
2. `playwright-upload.js:79-83` — `scrollIntoView` on `#upload` section
3. `playwright-upload.js:85-96` — Fill `#memberFirstName`, `#memberLastName`, `#memberNumber`, `#memberClaimId`, `#memberProvider`
4. `playwright-upload.js:99-107` — Click `#btnSaveMember`, await `#memberModal.active`, click `.member-modal-close`
5. `playwright-upload.js:110-115` — Scroll `.upload-form` into view
6. `playwright-upload.js:118-141` — `fileInput.setInputFiles(FILE_PATH)` on `input[name="notice"]`; validates `el.files.length > 0`
7. `playwright-upload.js:154-158` — `Promise.all([page.waitForNavigation(), uploadButton.click()])` — submits form, awaits `domcontentloaded`
8. `playwright-upload.js:160-169` — Await `.modal-confirmation` selector (success); fallback logs body text snippet
9. `playwright-upload.js:172-173` — Screenshot to `/tmp/upload-success-{timestamp}.png`
10. Returns `{success:true, file, timestamp}` on success; `{success:false, error, file}` on failure (`playwright-upload.js:192-196`)

**Exit codes:** `0` success, `1` failure (`playwright-upload.js:194`).

**Error screenshots:** saved to `/tmp/upload-error-{timestamp}.png` (`playwright-upload.js:184-185`).

---

## 4. EXTERNAL INTEGRATIONS

### Who calls this portal

OPA calls this portal via:
- `server/app/services/provider_portal_service.py` — `ProviderPortalService.upload_recoup_notice()` spawns `playwright-upload.js` as subprocess (or uses Python Playwright)
- `server/app/routes/provider_portal.py:17` — `POST /api/provider-portal/upload-recoup-notice` triggers the service

OPA env vars consumed by the OPA service to target this portal (set in `server/.env`):
- `PROVIDER_PORTAL_URL` — defaults to `http://localhost:3002`
- `PROVIDER_PORTAL_USER` — defaults to `provider`
- `PROVIDER_PORTAL_PASS` — defaults to `password`

### This portal's own integrations

- **No outbound HTTP calls.** The portal is entirely passive — it receives files; it does not push them to OPA or any other service.
- `uploads/` dir: files persist in `mock-provider-portal/uploads/` as `{epoch_ms}-{originalname}`. OPA does not read from this directory directly; OPA checks its own audit log (`AuditLog` rows with `action LIKE '%PORTAL_UPLOAD%'`) rather than polling the portal's `/api/status`.

### OPA audit trail

`server/app/routes/provider_portal.py:107-121` — every upload attempt (success or failure) writes an `AuditLog` row with `action='PORTAL_UPLOAD_RECOUP_NOTICE'` (or `_FAILED`), `meta_json` containing `provider_id`, `portal`, `file`, and `upload_result`.

---

## 5. CONFIG & ENV

### Portal service itself

| Item | Value | Source |
|---|---|---|
| Port | `3002` | `server.js:8` hardcoded |
| Session secret | `'mock-provider-secret'` | `server.js:32` hardcoded |
| Login credentials | `provider` / `password` | `server.js:50-51` hardcoded |
| Upload dir | `./uploads/` | `server.js:11` relative to `__dirname` |
| File naming | `{Date.now()}-{originalname}` | `server.js:22` |
| Accepted MIME | `.pdf,.txt,.doc,.docx` | HTML form `accept` attrs; multer has no type filter |
| Static files | `./public/` | `server.js:30` (`express.static`) — directory does not exist in repo, non-fatal |

### Env vars consumed by OPA to call this portal

Documented in `README.md:68-72`; read by `server/app/services/provider_portal_service.py`:

| Var | Default |
|---|---|
| `PROVIDER_PORTAL_URL` | `http://localhost:3002` |
| `PROVIDER_PORTAL_USER` | `provider` |
| `PROVIDER_PORTAL_PASS` | `password` |

### No `.env` file in this project

This service has no `.env` or config file — all config is hardcoded in `server.js`.

---

## 6. KNOWN ISSUES / GAPS / TODOs

1. **`headless: false` in playwright-upload.js:52** — The script always launches a visible browser window unless OPA's `ProviderPortalService` explicitly overrides this. In CI or headless Railway deploys this will fail unless the caller passes `headless=true` and the script is updated to honour it as a flag (it currently only reads args at line 26-31 but `headless` is not parsed from args — it is hardcoded).

2. **No multer file-type validation** — `server.js:17-25` configures only `diskStorage`; there is no `fileFilter`. Any file type can be uploaded regardless of the HTML `accept` attribute.

3. **Member info form is client-only** — Fields `#memberFirstName`, `#memberLastName`, `#memberNumber`, `#memberClaimId`, `#memberProvider` on `/dashboard` are rendered in HTML and saved client-side (JS `readonly` toggle). They are **not** submitted with the `/upload` POST form and are **never persisted** server-side. Playwright fills them for visual realism only; they have no effect on the uploaded file metadata.

4. **`public/` directory missing** — `server.js:30` calls `express.static('public')` but no `public/` dir exists in the repo. Express silently ignores this; no 500 error, but any intended static assets would 404.

5. **Uploaded files named by epoch prefix** — `server.js:22` `{Date.now()}-{originalname}`. The dashboard display at `server.js:271` strips the prefix via `f.name.split('-').slice(1).join('-')` which will mangle filenames that already contain `-`.

6. **No HTTPS / CSRF protection** — Session cookie is `httpOnly` but there is no `secure` flag and no CSRF token on forms. Acceptable for a local mock; not safe to expose publicly.

7. **`/api/status` unauthenticated** — `server.js:1297` has no `requireAuth`; any client can enumerate uploaded file names without logging in.

8. **`README.md:87-97` documents OPA API paths that depend on `server/app/routes/provider_portal.py` and `server/app/services/provider_portal_service.py`** — both files exist in the OPA repo as untracked (`??`) files, meaning they are not yet committed and may not be wired into OPA's router in `main.py`.
