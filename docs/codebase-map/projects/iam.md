# IAM — Identity & Access Management: Machine-Readable Context Map

> Agent reference file. Dense, factual. Every code claim carries `relative/path:line`.

---

## 1. IDENTITY

| Field | Value |
|---|---|
| **Path** | `/Users/issamzeinoun/claude/iam` |
| **Purpose** | Centralized admin UI for the Payment Integrity Platform. Manages users, roles, app grants, connectors, and member reference data across PayGuard, ClaimGuard, SIU, FWA, COB. |
| **Stack** | React 18 + Vite 6 + TypeScript + Tailwind 3 + TanStack Query v5 + Axios 1.7 |
| **Entrypoint** | `frontend/src/main.tsx:1` — mounts `<DemoGate><App /></DemoGate>` |
| **Port** | `5177` (dev: `vite --port 5177 --strictPort`; prod: `serve -s dist -l ${PORT:-5177}`) |
| **Run scripts** | `npm run dev` (Vite dev server), `npm run build`, `npm run start` (serve built SPA) |
| **Backend** | No dedicated backend. Calls OPA unified backend at `http://localhost:8001` (dev) / `https://payguard.penguinai.studio` (prod). Configured in `frontend/src/config/appUrls.ts:14-20`. |

---

## 2. STRUCTURE

```
iam/
├── README.md                          # Minimal ("# iam")
├── frontend/
│   ├── README.md                      # Architecture overview; lists pages + backend endpoints
│   ├── package.json                   # npm scripts + deps (react, axios, tanstack-query)
│   ├── vite.config.ts                 # port 5177 + react plugin
│   ├── index.html                     # SPA shell
│   ├── dist/                          # Production build output (deployed artifact)
│   └── src/
│       ├── main.tsx                   # App root: QueryClient + DemoGate wrapper
│       ├── App.tsx                    # Tabbed shell: sidebar nav + header (AppSwitcher + ActorPicker)
│       ├── DemoGate.tsx               # Shared-password login wall (mirrors OPA's demo gate)
│       ├── index.css                  # Tailwind directives
│       ├── vite-env.d.ts
│       ├── api/
│       │   ├── client.ts              # Axios instance; X-User-Id + demo token interceptors; 401 handler
│       │   ├── index.ts               # `api` object: all CRUD methods (users/roles/apps/connectors/members)
│       │   └── types.ts               # TS interfaces: User, Role, App, Connector, Member
│       ├── config/
│       │   └── appUrls.ts             # Committed URL map: DEV/PROD switch by import.meta.env.PROD
│       ├── components/
│       │   ├── ActorPicker.tsx        # "Acting as" dropdown; writes iam.actorUserId to localStorage
│       │   ├── AppSwitcher.tsx        # Cross-app nav bar; reads VITE_* env vars (NOT appUrls.ts)
│       │   ├── EnvironmentBanner.tsx  # Dev (green) vs prod (red) banner
│       │   ├── ConnectorFormModal.tsx # Create/edit connector form
│       │   ├── ConnectorRunHistory.tsx# Run history panel per connector
│       │   ├── EditUserModal.tsx      # Edit user profile/status/default_app
│       │   └── NewUserModal.tsx       # Create user + assign roles
│       └── pages/
│           ├── UsersPage.tsx          # User list + inline role assign/revoke + toggle active
│           ├── RolesPage.tsx          # Role cards + inline app grant/revoke + new role modal
│           ├── AppsPage.tsx           # App cards + active toggle + user count + new app
│           ├── ConnectorsPage.tsx     # HTTP/SFTP/internal/webhook connector management + test + history
│           └── MembersPage.tsx        # Shared member reference data (paginated CRUD)
```

---

## 3. PAGES / ROUTES

IAM has **no React Router**. Navigation is tab state (`useState<Tab>`) in `App.tsx:14`.

| Tab key | File:line | Purpose | Backend endpoints |
|---|---|---|---|
| `users` | `pages/UsersPage.tsx:26` | List/search/toggle/edit users; inline role assign/revoke | `GET/POST /api/users`, `PATCH /api/users/{id}`, `POST/DELETE /api/users/{id}/roles/{roleId}` |
| `roles` | `pages/RolesPage.tsx:14` | Role cards; edit name/desc; grant/revoke app access per role | `GET /api/roles`, `POST /api/roles`, `PATCH /api/roles/{id}`, `POST/DELETE /api/roles/{id}/apps/{appId}` |
| `apps` | `pages/AppsPage.tsx:14` | Registered apps; edit; toggle active; show user count | `GET /api/apps`, `POST /api/apps`, `PATCH /api/apps/{id}` |
| `connectors` | `pages/ConnectorsPage.tsx:30` | Platform integrations: HTTP/SFTP/webhook/internal; test + run history | `GET/POST /api/connectors`, `PATCH/DELETE /api/connectors/{id}`, `POST /api/connectors/{id}/test`, `POST /api/connectors/{id}/run`, `GET /api/connectors/{id}/runs` |
| `members` | `pages/MembersPage.tsx:22` | Shared member reference data (paginated; LOB filter) | `GET/POST /api/members`, `PUT /api/members/{id}`, `DELETE /api/members/{id}` |

No dedicated login page. Auth is handled by `DemoGate.tsx` wrapping the entire app.

---

## 4. AUTH MODEL

### Reality vs. Plans

IAM is **NOT** the central SSO provider today. The `CROSS_APP_AUTH.md` (Phase 5) plans to make IAM the canonical login page, but this is unimplemented. IAM is a consumer of the OPA backend's demo gate, same as every other app.

### Two parallel credential mechanisms

**Mechanism A — Demo gate password (shared secret)**
- On mount, `DemoGate.tsx:21` calls `GET /api/auth/status` to check if `gate_enabled`.
- If locked: shows password form; `POST /api/auth/login { password }` → stores `res.data.token` in `localStorage['opa_demo_token']` (`DemoGate.tsx:10,36`).
- Axios interceptor (`api/client.ts:26-27`) attaches it as `Authorization: Bearer <token>` on all requests.
- Token is OPA's stateless HMAC `<exp>.<sig>` format, 12h TTL (per OPA CLAUDE.md).
- On 401 where response body is NOT "Unknown user_id": `localStorage.removeItem('opa_demo_token')` + `window.location.reload()` (`api/client.ts:52-57`).

**Mechanism B — Actor identity (demo user switcher, NOT real auth)**
- `ActorPicker.tsx:16`: stores selected user UUID in `localStorage['iam.actorUserId']`.
- Axios interceptor (`api/client.ts:17-23`) attaches it as `X-User-Id` header on ALL requests, plus `actor_user_id` query param on POST/PATCH/DELETE mutations (for audit `granted_by_user_id` in backend).
- Default actor auto-selected to first `admin`-role user from `GET /api/users` (`ActorPicker.tsx:60-67`).
- On 401 with "Unknown user_id" in response body: `localStorage.removeItem('iam.actorUserId')` + reload (`api/client.ts:50-51`). This handles stale actor after backend re-seed.
- This is a demo identity selector, NOT authentication. Anyone can act as any user.

**Mechanism C — SSO cookie (passive)**
- `api/client.ts:10`: `withCredentials: true` — Axios sends the `opa_token` httpOnly cookie automatically on all requests.
- No active auth flow for this in IAM; it piggybacks on a cookie set by another app (PayGuard or OPA Assistant).
- No `authService.ts` exists in IAM despite `CROSS_APP_SSO_COMPLETE.md:274` claiming it was added. The file is absent from the codebase.

### Reentrancy guard
- `api/client.ts:32`: `sessionStorage['iam.authReloading']` prevents infinite reload on persistent 401. Cleared on first successful response.

### How other apps consume IAM identity
- No redirect-based SSO. Other apps do NOT redirect to IAM for login.
- OPA backend (`/api/users`, `/api/roles`) is the shared user store; IAM admins it.
- Identity propagation is via the shared `X-User-Id` header convention + httpOnly cookie (when set by another app).

---

## 5. API LAYER

**Base URL resolution** (`frontend/src/config/appUrls.ts:32-35`):
- Dev: `http://localhost:8001`
- Prod: `https://payguard.penguinai.studio`
- Selection: `import.meta.env.PROD` (Vite build mode, NOT a runtime env var)

**Axios client**: `frontend/src/api/client.ts:7-11`

**All API methods**: `frontend/src/api/index.ts`

| Method | Endpoint | Purpose |
|---|---|---|
| `listUsers(includeInactive)` | `GET /api/users?include_inactive=` | User list |
| `getUser(id)` | `GET /api/users/{id}` | Single user |
| `createUser(body)` | `POST /api/users` | Create user |
| `updateUser(id, body)` | `PATCH /api/users/{id}` | Edit profile/status/default_app |
| `assignRole(userId, roleId)` | `POST /api/users/{userId}/roles/{roleId}` | Grant role |
| `revokeRole(userId, roleId)` | `DELETE /api/users/{userId}/roles/{roleId}` | Revoke role |
| `listUserRoles(userId)` | `GET /api/users/{userId}/roles` | User's roles |
| `listApps(includeInactive)` | `GET /api/apps?include_inactive=` | App list |
| `createApp(name, desc)` | `POST /api/apps` | Register app |
| `updateApp(id, body)` | `PATCH /api/apps/{id}` | Edit/toggle app |
| `listRoles()` | `GET /api/roles` | All roles |
| `createRole(name, desc, appIds)` | `POST /api/roles` | New role with initial app grants |
| `updateRole(id, body)` | `PATCH /api/roles/{id}` | Edit role |
| `grantAppToRole(roleId, appId)` | `POST /api/roles/{roleId}/apps/{appId}` | Grant app to role |
| `revokeAppFromRole(roleId, appId)` | `DELETE /api/roles/{roleId}/apps/{appId}` | Revoke app from role |
| `listConnectors(opts)` | `GET /api/connectors` | Connector list |
| `getConnector(id)` | `GET /api/connectors/{id}` | Single connector |
| `createConnector(body)` | `POST /api/connectors` | New connector |
| `updateConnector(id, body)` | `PATCH /api/connectors/{id}` | Edit connector |
| `deleteConnector(id)` | `DELETE /api/connectors/{id}` | Remove connector |
| `testConnector(id, input)` | `POST /api/connectors/{id}/test` | Test without logging |
| `runConnector(id, input)` | `POST /api/connectors/{id}/run` | Run with logging |
| `listConnectorRuns(id, limit)` | `GET /api/connectors/{id}/runs` | Run history |
| `listMembers(opts)` | `GET /api/members` | Paginated member list |
| `createMember(body)` | `POST /api/members` | New member |
| `updateMember(id, body)` | `PUT /api/members/{id}` | Edit member |
| `deleteMember(id)` | `DELETE /api/members/{id}` | Remove member |

**Auth endpoints** (used by DemoGate only):
- `GET /api/auth/status` — check if gate_enabled (`DemoGate.tsx:21`)
- `POST /api/auth/login { password }` — get demo token (`DemoGate.tsx:35`)

**Response shapes** (from `frontend/src/api/types.ts`):

```typescript
User { id: string, name: string, username: string|null, email: string|null,
       role: string, is_active: boolean, initials: string|null,
       color_hex: string|null, specialty: string|null, supervisor_id: string|null,
       roles: string[], apps: string[], default_app: string|null, default_app_id: string|null }

Role { id: string, name: string, description: string, apps: string[] }

App  { id: string, name: string, description: string, is_active: boolean }

Connector { connector_id: string, name: string, kind: 'http'|'sftp'|'internal'|'webhook',
            direction: 'inbound'|'outbound', is_active: boolean, config: {}, secret_keys: {},
            input_schema: {}|null, mock_enabled: boolean, mock_response: {}|null, ... }

Member { member_id: string, member_number: string, first_name: string, last_name: string,
         date_of_birth: string, lob: string, coverage_effective_date: string,
         coverage_termination_date: string|null, created_at: string, updated_at: string }

MemberListResponse { total: number, items: Member[] }
```

---

## 6. EXTERNAL INTEGRATIONS

### Outbound (backends called)

| Target | File:line | Env var | Notes |
|---|---|---|---|
| OPA backend (dev) | `config/appUrls.ts:24` | None (committed) | `http://localhost:8001` |
| OPA backend (prod) | `config/appUrls.ts:16` | None (committed) | `https://payguard.penguinai.studio` |

No other backends. IAM does not call any external services directly.

### Cross-app navigation (AppSwitcher)

`frontend/src/components/AppSwitcher.tsx` links to:

| App | Dev default | Env var override |
|---|---|---|
| IAM Admin | `http://localhost:5177` | `VITE_IAM_URL` |
| PayGuard | `http://localhost:5174` | `VITE_PAYGUARD_URL` |
| ClaimGuard | `http://localhost:5175` | `VITE_CLAIMGUARD_URL` |
| SIU | `http://localhost:5178` | `VITE_SIU_URL` |

Note: AppSwitcher reads `import.meta.env.VITE_*` directly (`AppSwitcher.tsx:6`), NOT the committed `config/appUrls.ts` map — inconsistency with other components that use `appUrls.ts`.

`config/appUrls.ts` also lists `assistant: http://localhost:5179` / `https://assistant.penguinai.studio` but the AppSwitcher does NOT show the assistant link (`AppSwitcher.tsx:8-13`).

### Who redirects to IAM / consumes IAM's identity output

- **Nobody redirects to IAM** for login today. There is no SSO redirect flow.
- The other apps (PayGuard, ClaimGuard, SIU, Assistant) each have their own login/demo-gate.
- IAM's only cross-app identity propagation is: (a) the shared OPA user database, (b) the `opa_token` httpOnly cookie written by PayGuard/Assistant login that IAM passively receives.

---

## 7. CONFIG & ENV

### Runtime env vars

| Var | Used by | Purpose | Required? |
|---|---|---|---|
| `VITE_IAM_URL` | `AppSwitcher.tsx:9` | IAM self-link in nav | No (fallback: localhost:5177) |
| `VITE_PAYGUARD_URL` | `AppSwitcher.tsx:10` | PayGuard nav link | No (fallback: localhost:5174) |
| `VITE_CLAIMGUARD_URL` | `AppSwitcher.tsx:11` | ClaimGuard nav link | No (fallback: localhost:5175) |
| `VITE_SIU_URL` | `AppSwitcher.tsx:12` | SIU nav link | No (fallback: localhost:5178) |
| `VITE_ENVIRONMENT` | `EnvironmentBanner.tsx:7` | Force prod/dev banner | No |
| `PORT` | `package.json:start` | Serve port in Railway | No (fallback: 5177) |

### Committed config (NOT env vars)

`frontend/src/config/appUrls.ts` — API base URL switches by `import.meta.env.PROD` (Vite build mode, not a deploy variable). No `.env.local` needed for API URL; README's `VITE_API_BASE_URL` mention is superseded by this committed file.

### No .env file in repo

No `.env` or `.env.local` checked in. The Railway deploy uses `PORT` for the serve command.

---

## 8. KNOWN ISSUES / GAPS / TODOs

### Security gaps

1. **Demo identity selector, not real auth.** `ActorPicker` lets any user claim any identity by selecting from a dropdown. `X-User-Id` is trusted by the backend with no cryptographic verification. RBAC enforcement is only as strong as the frontend's willingness to send the correct header.

2. **Demo gate is shared-password, not per-user auth.** `opa_demo_token` is a single shared secret. All IAM admin users get the same access level if they know the password. There is no per-user session for IAM's own login.

3. **No password hashing.** Per OPA CLAUDE.md: "currently username=password for demo." Anyone who can inspect the seeded users can authenticate as any of them.

4. **`authService.ts` claimed but missing.** `CROSS_APP_SSO_COMPLETE.md:274` states a `services/authService.ts` was added to IAM. It does NOT exist (`find` result shows no `services/` directory). The SSO cookie works passively (withCredentials) but IAM has no active session management (no `initAuth()`, no refresh timer, no BroadcastChannel listener).

5. **Stale actor reentrancy guard is sessionStorage, not durable.** If the guard is set and the tab is refreshed, `sessionStorage.removeItem(RELOAD_GUARD_KEY)` is called on the next successful response — but a reload loop could still happen if no request ever succeeds (`api/client.ts:43-57`).

### Auth/SSO architecture gaps

6. **IAM is NOT the SSO provider** (planned as Phase 5 in CROSS_APP_AUTH.md). Currently there is no redirect-back flow, no token issuance from IAM, no central login page. Each app (PayGuard, Assistant) does its own login against `/api/auth/login` independently.

7. **AppSwitcher inconsistency.** `AppSwitcher.tsx` reads `VITE_*` env vars; `config/appUrls.ts` has committed URLs that switch by build mode. These two patterns coexist — an agent changing one won't automatically update the other. The Assistant link is in `appUrls.ts` but NOT in `AppSwitcher`.

8. **No route guarding.** There is no React Router, so there is no route-level access control. All 5 tabs are always rendered (DemoGate gates the whole app, but there's no per-tab RBAC in the UI — the backend enforces it on API calls).

9. **Members tab requires admin role.** Backend gates `DELETE /api/members/{id}` and creates on `require_role("admin")` per `MembersPage.tsx:3-4` comment. The UI shows all operations to all users who pass the demo gate; 403s surface as error messages only.

10. **Prod API URL is payguard.penguinai.studio, not a dedicated IAM backend.** `config/appUrls.ts:16`: `apiBase: 'https://payguard.penguinai.studio'`. IAM admin shares the PayGuard Railway service. No isolation between admin and non-admin API traffic.
