# Codebase Map — assistant (standalone frontend)

Machine-readable context for AI coding agents. Dense, factual, no filler.
Generated: 2026-06-29. Source: `/Users/issamzeinoun/claude/assistant`.

---

## 1. IDENTITY

| Field | Value |
|---|---|
| Path | `/Users/issamzeinoun/claude/assistant` |
| Purpose | Standalone full-page OPA Assistant UI — chat + interactive cockpit for payment-integrity work (PayGuard post-pay). No backend of its own. |
| Stack | Vite 6 + React 18 + TypeScript 5.7 + Tailwind 3 + TanStack Query v5 + Axios + ReactMarkdown + DOMPurify |
| Entrypoint | `frontend/src/main.tsx:1` → `Root` → `LoginPage` or `App` |
| Dev port | `5179` (`vite.config.ts:7`, `package.json` scripts) |
| Prod URL | `https://assistant.penguinai.studio` (`src/config/appUrls.ts:15`) |
| Backend | OPA unified backend at `:8001` (dev) / `https://payguard.penguinai.studio` (prod) — same server as PayGuard |
| Run scripts | `npm run dev` → Vite :5179; `npm run build` → tsc + vite; `npm run start` → `serve -s dist` |
| Deploy | Railway — `frontend/railway.json`: `npm run build` / `npm run start`, healthcheck `/` |
| No env vars | URLs hard-coded in `src/config/appUrls.ts`; switches by `import.meta.env.PROD`. No `VITE_*` vars. |

---

## 2. STRUCTURE

```
assistant/
├── README.md                  # Project overview + deploy instructions
├── docs/
│   ├── interactive-cockpit.md # Design doc: cockpit P0–P3 phases + locked decisions
│   └── Demo cases to show     # QA note for demo prompt
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.ts
    ├── railway.json
    └── src/
        ├── main.tsx           # Root — auth gate, QueryClientProvider
        ├── App.tsx            # Top bar + <AssistantChat/>
        ├── index.css
        ├── vite-env.d.ts
        ├── api/
        │   ├── client.ts      # axios instance + 401 reload interceptor
        │   ├── index.ts       # All API calls (typed); countCases, listCases, getCase, etc.
        │   └── types.ts       # All shared TS types (User, Directive, CaseSummary, CaseDetailLite, CaseGuidance, …)
        ├── config/
        │   └── appUrls.ts     # Committed URL map (DEV/PROD); appUrl() helper
        ├── services/
        │   └── authService.ts # Cookie-based JWT: login/logout/refresh/BroadcastChannel
        ├── lib/
        │   ├── nextAction.ts        # CockpitActionReq type; instructionForAction()
        │   └── sanitizeAssistantOutput.ts  # Strip ``` blocks + @@FOLLOWUPS@@ markup
        ├── pages/
        │   └── LoginPage.tsx  # username/password form → POST /api/auth/login
        └── components/
            ├── AssistantChat.tsx     # Main orchestrator: SSE stream, state machine, render
            ├── Launchpad.tsx         # Role-aware action buttons with live counts
            ├── ViewSurface.tsx       # Dispatch directive → worklist/case/my_dashboard/briefing
            ├── LeftNav.tsx           # Collapsible sidebar: quick links (high-priority, pending-review, my-cases)
            ├── CockpitActionBar.tsx  # Case-level action pills; confirm step for irreversibles
            ├── CaseLifecycleRail.tsx # Horizontal/vertical lifecycle stepper (mirrors PayGuard)
            ├── AppSwitcher.tsx       # Links to IAM/PayGuard/ClaimGuard/SIU
            ├── ActorPicker.tsx       # Demo user switcher → localStorage assistant_user_id
            ├── EnvironmentBanner.tsx # Dev/prod visual indicator
            └── views/
                ├── WorklistMini.tsx      # Compact case table; "Open in PayGuard" deep-link
                ├── CaseCockpit.tsx       # Full tabbed case view with inline write actions
                ├── MyDashboardView.tsx   # Stat tiles from /api/dashboard/me
                └── BriefingLandingPage.tsx  # Daily briefing: personal stats, trends, team vs. you, high-value queue
```

---

## 3. PAGES / COMPONENTS

### Routing
No client-side router. Single-page app. Auth state (`isAuthenticated`) in `main.tsx:16` controls whether `LoginPage` or `App` renders. No URL routes.

### Components

| Component | File:line | Purpose |
|---|---|---|
| `Root` | `main.tsx:15` | Auth init via `initAuth`; gates App vs. LoginPage |
| `LoginPage` | `pages/LoginPage.tsx:5` | Form → `login()` → sessionStorage `assistant_user_id` |
| `App` | `App.tsx:7` | Top bar (logo, env indicator, AppSwitcher, user chip, logout) + `<AssistantChat/>` |
| `AssistantChat` | `components/AssistantChat.tsx:67` | Full chat orchestrator: SSE read loop, state machine (stream/awaiting/confirming/pendingInput/activeView), inline write execution |
| `Launchpad` | `components/Launchpad.tsx:79` | Role-aware buttons (ANALYST vs. SUPERVISOR specs); dispatches `Directive` client-side (no agent round-trip); live counts via `api.countCases` |
| `ViewSurface` | `components/ViewSurface.tsx:28` | Mounts view by `directive.view`: worklist/case/my_dashboard/briefing |
| `WorklistMini` | `components/views/WorklistMini.tsx:35` | Paginated case table; "My cases" merges assigned + unassigned; deep-links to PayGuard |
| `CaseCockpit` | `components/views/CaseCockpit.tsx:62` | 6 tabs (overview/notes/evidence/disputes/era/output); action pills → `onAction` → `AssistantChat.runCockpitAction`; "Open full case" → PayGuard deep-link |
| `MyDashboardView` | `components/views/MyDashboardView.tsx:25` | Stat tiles from `/api/dashboard/me`; period param |
| `BriefingLandingPage` | `components/views/BriefingLandingPage.tsx:16` | Daily briefing: 4 stat cards, trends, team comparison bar chart, priority work queue |
| `CockpitActionBar` | `components/CockpitActionBar.tsx` | Server-driven `CaseAction[]` → pills; `CONFIRM_KINDS = {send_notice, supervisor_approve}` get an armed-confirm step |
| `CaseLifecycleRail` | `components/CaseLifecycleRail.tsx` | Lifecycle stepper mirroring PayGuard; driven by `CaseGuidance.lifecycle[]` |
| `ActorPicker` | `components/ActorPicker.tsx:38` | User list from `/api/users`; stores id in `localStorage('assistant_user_id')`; reloads on switch |
| `AppSwitcher` | `components/AppSwitcher.tsx:14` | Nav links to IAM/PayGuard/ClaimGuard/SIU (hrefs from `appUrls.ts`) |
| `LeftNav` | `components/LeftNav.tsx` | Fixed sidebar; "high-priority/pending-review/my-cases" → `onNavigate` → `sendPrompt` in AssistantChat |

### Chat/assistant UI flow

1. `main.tsx` calls `initAuth()` → checks `/api/auth/me` cookie; if unauthenticated → `LoginPage`.
2. `LoginPage` POSTs `/api/auth/login` → httpOnly cookie set; writes `user_id` to `sessionStorage`.
3. `App` renders `<AssistantChat/>`.
4. `AssistantChat` mounts `<Launchpad>` (live counts) above the chat scroll area.
5. User clicks Launchpad button → `dispatchView(directive)` → `setActiveView` → `<ViewSurface>` mounts inline.
6. User types prompt → `send(messages)` → SSE fetch to `/api/assistant/chat/stream`.
7. SSE events parsed in `handleEvent()`:
   - `assistant_text` → append to `stream` → `<AssistantBubble>` (streaming)
   - `tool_start`/`tool_end` → `<ToolLine>` indicator
   - `directive` → `setActiveView` → surface mode mount
   - `awaiting_user` → show option buttons; user picks → `tool_result` sent back
   - `awaiting_confirmation` → show Confirm/Cancel gate; user confirms → `tool_result: "CONFIRMED"`
   - `final` → replace `messages`, clear stream, show `suggestions`
8. Cockpit action pill click → `runCockpitAction(CockpitActionReq)` → immediate API call or `pendingInput` to capture amount/reason via chat box.
9. All writes invalidate `queryKey: ['cockpit-case']` to refresh cockpit.

---

## 4. API LAYER

### Base URL
`API_BASE_URL` from `src/config/appUrls.ts:35`:
- DEV: `http://localhost:8001`
- PROD: `https://payguard.penguinai.studio`

No trailing slash, no `/api` suffix (appended per-call).

### HTTP client
`src/api/client.ts:7` — axios instance with `withCredentials: true`; 401 interceptor reloads page (except `/auth/` calls).

### Endpoints called

| Method | Path | File:line | Purpose |
|---|---|---|---|
| `POST` | `/api/auth/login` | `services/authService.ts:53` | Login; sets httpOnly cookie |
| `POST` | `/api/auth/logout` | `services/authService.ts:91` | Logout |
| `POST` | `/api/auth/refresh` | `services/authService.ts:124` | Token refresh (every 11h) |
| `GET` | `/api/auth/me` | `services/authService.ts:37` | Current user check |
| `POST` | `/api/assistant/chat/stream` | `components/AssistantChat.tsx:117` | Main SSE stream; body: `{messages, context}` |
| `GET` | `/api/users` | `api/index.ts:33` | User list for ActorPicker/Launchpad |
| `GET` | `/api/cases` | `api/index.ts:37` | Case list; params: `page_size, exclude_closed, status, priority, overdue_only, assignee_id, scope` |
| `GET` | `/api/cases/{id}` | `api/index.ts:51` | Case detail (full `CaseDetailLite` with guidance, findings, notes, notices, disputes) |
| `GET` | `/api/dashboard/me` | `api/index.ts:55` | Personal dashboard stats |
| `GET` | `/api/dashboard/briefing` | `api/index.ts:60` | Daily briefing (personal_stats, trends, team_comparison, high_value_cases) |
| `GET` | `/api/documents` | `api/index.ts:67` | Case documents (param: `case_id` UUID) |
| `GET` | `/api/claims/{claimId}/evidence-findings` | `api/index.ts:73` | AI evidence findings for claim |
| `POST` | `/api/documents` | `api/index.ts:87` | Upload document (multipart; fields: file, claim_id, kind) |
| `POST` | `/api/claims/{claimId}/validate-evidence` | `api/index.ts:95` | Trigger evidence analysis |
| `POST` | `/api/cases/{id}/notes` | `api/index.ts:106` | Add case note |
| `PATCH` | `/api/cases/{id}/assign` | `api/index.ts:110` | Assign case to analyst |
| `POST` | `/api/cases/{id}/transition` | `api/index.ts:113` | Status transition |
| `POST` | `/api/cases/{id}/escalate` | `api/index.ts:117` | Escalate case |
| `POST` | `/api/cases/{id}/rerun-detectors` | `api/index.ts:120` | Re-run detectors |
| `POST` | `/api/findings/{id}/accept` | `api/index.ts:125` | Accept finding |
| `POST` | `/api/findings/{id}/reject` | `api/index.ts:128` | Reject finding (body: `{reason}`) |
| `POST` | `/api/findings/{id}/adjust` | `api/index.ts:131` | Adjust finding amount |
| `POST` | `/api/cases/{id}/approve` | `api/index.ts:136` | Supervisor approve |
| `POST` | `/api/cases/{id}/reject` | `api/index.ts:139` | Supervisor reject |
| `POST` | `/api/cases/{id}/reopen` | `api/index.ts:142` | Reopen case |
| `POST` | `/api/cases/{id}/adjudicate-without-claim` | `api/index.ts:145` | Adjudicate without 837 |
| `POST` | `/api/siu/escalate` | `api/index.ts:148` | SIU escalation (body: `{case_id: UUID, escalation_reason}`) |

### Stream endpoint shape

**Request** (`POST /api/assistant/chat/stream`):
```json
{
  "messages": [{"role": "user"|"assistant", "content": string | ContentBlock[]}],
  "context": {"active_case_id"?: number, "active_view"?: string}
}
```

**SSE events** (each `data: <JSON>\n\n`):
| `type` | Payload fields | Effect |
|---|---|---|
| `assistant_text` | `text: string` | Append streaming text bubble |
| `tool_start` | `id, name` | Show tool indicator (running) |
| `tool_end` | `id, ok: bool, error?` | Update tool indicator |
| `directive` | `view, params, caption` | Mount ViewSurface |
| `awaiting_user` | `messages, question, options[], tool_use_id` | Show option buttons; respond with `tool_result` |
| `awaiting_confirmation` | `messages, summary, preview?, action, tool_use_id` | Show Confirm/Cancel; respond `"CONFIRMED"` or `"CANCELLED"` |
| `final` | `messages, suggestions[]` | Replace history; show follow-up chips |
| `error` | `error: string` | Show error banner |

---

## 5. ASSISTANT MECHANICS

### State model (`AssistantChat.tsx:68–81`)
```
messages: Message[]          // Full Anthropic conversation history (client-side, stateless server)
stream: StreamItem[]         // In-flight token/tool events (cleared on 'final')
awaiting: Awaiting | null    // ask_user mid-turn (question + options + tool_use_id)
confirming: Confirming | null // write gate (summary + action + tool_use_id)
pendingInput: PendingInput | null // cockpit action waiting for amount/reason via chat box
activeView: Directive | null // mounted ViewSurface
loading: boolean
suggestions: string[]        // follow-up chips from 'final'
```

### Conversation threading
Stateless backend — full `messages[]` sent on every request (Anthropic message format). No server-side session/thread storage. History is React state; lost on page reload.

### Tool call rendering
- `ask_user` tool_use blocks → tracked in `askUserIds` Set → the corresponding user `tool_result` renders as a user bubble (`AssistantChat.tsx:344–350`).
- All other `tool_result` blocks (real tool output) → suppressed from UI (prevented the "raw JSON dumped in chat" bug).
- `tool_use` blocks in assistant messages → `<ToolLine>` with tool name.
- `present_view` → never shown in chat; triggers `setActiveView` via `'directive'` SSE event.

### Write gate (confirmation flow)
`awaiting_confirmation` event → `Confirming` state → Confirm/Cancel UI → user responds with `tool_result: "CONFIRMED"` or `"CANCELLED"` → `send(next)`. Backend executes write only on `CONFIRMED`. `AssistantChat.tsx:222–232`.

### Dual render modes
- **Surface mode**: agent emits `present_view` tool → backend emits `directive` SSE → `setActiveView` → `<ViewSurface>` mounts. Launchpad buttons dispatch same `Directive` client-side (no agent round-trip).
- **Prose mode**: standard markdown/HTML answer. HTML-card detection (`HTML_CARD` regex) → `DOMPurify.sanitize` render vs. `<ReactMarkdown>` with remark-gfm + rehype-raw.

### Context injection
`context` object derived from `activeView` (`AssistantChat.tsx:87–93`):
- `{active_case_id: N, active_view: 'case'}` when a case is open
- `{active_view: view}` otherwise
Sent with every stream request so the agent can resolve "this case" references.

### User identity storage (inconsistency)
- `ActorPicker.tsx:39` + `Launchpad.tsx:81`: reads/writes `localStorage('assistant_user_id')`
- `LoginPage.tsx:19` + `AssistantChat.tsx:246` (`runCockpitAction`): reads/writes `sessionStorage('assistant_user_id')`
- **Bug**: two different storage keys — actor picked via ActorPicker may not match identity used in `runCockpitAction`.

---

## 6. EXTERNAL INTEGRATIONS

### OPA backend
Primary target. Every API call goes to `API_BASE_URL` (`appUrls.ts:35`). No separate assistant backend.

### ClearLink
Not directly called from frontend. Accessed via OPA assistant agent as a tool. The "Member Record" quick-action button (`AssistantChat.tsx:335`) sends a natural-language prompt to the agent asking it to "show me `{memberName}`'s ClearLink record … use member ID: `{memberNumber}`". The agent then invokes ClearLink tools server-side (opa/server/app/services/assistant/tools.py). Frontend has no direct ClearLink SDK/fetch.

### PayGuard app (deep-links)
`appUrl('payguard', 'cases/{id}')` → `https://payguard.penguinai.studio/cases/{id}` — opens full case in PayGuard in a new tab. `CaseCockpit.tsx:78`, `WorklistMini.tsx:75`. Not an API call — plain `<a target="_blank">` links.

### Cross-app auth sync
`services/authService.ts:173` — `BroadcastChannel('opa_auth')` broadcasts `auth:login`, `auth:logout`, `auth:expired` to other platform apps at same origin.

---

## 7. RELATION TO OPA & CLEARLINK

### Is this the standalone assistant frontend?
Yes. The README (`README.md:1`) confirms: "Full-page, read-only chat over the OPA payment-integrity platform."

### Same backend as embedded PayGuard assistant
Both this app and OPA's embedded `client/src/components/assistant/AssistantPanel.tsx` call the **same endpoint**: `POST /api/assistant/chat/stream` on the same OPA backend (`server/app/services/assistant/`). The standalone app is a separate deploy; the embedded panel is a drawer inside PayGuard. No code is shared between the two frontends.

### Differences from embedded AssistantPanel
| Aspect | Standalone (`/assistant`) | Embedded (`AssistantPanel.tsx`) |
|---|---|---|
| Deploy | Separate Railway service | Bundled inside PayGuard client |
| Layout | Full-page; Launchpad + ViewSurface above chat | Side-panel drawer |
| Views | worklist/case/my_dashboard/briefing as native components | N/A (panel is chat-only) |
| Write actions | Inline via `runCockpitAction` | Via agent only |
| Auth | Cookie-based JWT + BroadcastChannel | X-User-Id header (demo gate) |
| Context | `{active_case_id, active_view}` | Likely `{case_id}` from PayGuard page |

### ClearLink relation
ClearLink tools are registered in `server/app/services/assistant/tools.py` and invoked by the OPA agent. The standalone assistant surfaces ClearLink data purely through the agent's prose/tool responses — there is no direct frontend-to-ClearLink call. Design doc (`docs/interactive-cockpit.md:20`) notes ClaimGuard/SIU native views as "follow-on track, not v1."

---

## 8. CONFIG & ENV

| Item | Value | Source |
|---|---|---|
| Dev API base | `http://localhost:8001` | `appUrls.ts:24` |
| Prod API base | `https://payguard.penguinai.studio` | `appUrls.ts:15` |
| Vite build mode | `import.meta.env.PROD` (auto, no var needed) | `appUrls.ts:32` |
| `VITE_ENVIRONMENT` | Optional; `EnvironmentBanner.tsx` checks it for prod label | `EnvironmentBanner.tsx:6` |
| No other env vars | Confirmed in README: "no env vars" | `README.md:13` |
| Railway deploy | `frontend/railway.json`: build=`npm run build`, start=`npm run start` | `railway.json` |
| Prod domain | `assistant.penguinai.studio` (add in Railway) | `README.md:37` |

---

## 9. KNOWN ISSUES / GAPS / TODOs

| # | Issue | Location |
|---|---|---|
| 1 | **localStorage vs sessionStorage split**: `ActorPicker` and `Launchpad` use `localStorage('assistant_user_id')`; `LoginPage` and `runCockpitAction` use `sessionStorage('assistant_user_id')`. Actor switch may not propagate to write actions. | `ActorPicker.tsx:39`, `LoginPage.tsx:19`, `AssistantChat.tsx:246` |
| 2 | **Chat history lost on reload**: conversation is React state only; `LeftNav` has a "Chat History" section marked "Coming soon". | `LeftNav.tsx` |
| 3 | **ActorPicker renders but App uses cookie user**: `App.tsx` fetches `getCurrentUser()` from cookie, not from `localStorage`. The header user chip and ActorPicker may show different users. | `App.tsx:12`, `ActorPicker.tsx` |
| 4 | **No useAssistantChat hook**: AssistantChat logic is duplicated vs. PayGuard's embedded AssistantPanel. Design doc flags `useAssistantChat` as a "Follow-on" shared hook. | `docs/interactive-cockpit.md:103` |
| 5 | **VITE_ENVIRONMENT inconsistency**: `EnvironmentBanner.tsx` checks `VITE_ENVIRONMENT` but README says "no env vars to manage." The banner also checks `window.location.hostname`, so it works without the var. | `EnvironmentBanner.tsx:6` |
| 6 | **ClearLink views not built**: design doc scopes ClaimGuard/SIU native views as "non-goals v1". ClearLink data only accessible via prose agent response. | `docs/interactive-cockpit.md:108` |
| 7 | **iframe escape hatch not built**: Phase 3 (iframe for full-fidelity PayGuard pages) is design-only. | `docs/interactive-cockpit.md:99` |
| 8 | **No `@penguin/ui` shared package**: CaseLifecycleRail and CockpitActionBar are copy-adapted from PayGuard; any PayGuard update diverges silently. | `docs/interactive-cockpit.md:103` |
| 9 | **LeftNav always defaults to open**: opens on mount; may conflict with narrow viewports. No persistent collapsed state. | `LeftNav.tsx:10` |
| 10 | **WorklistMini "My cases" over-fetches**: when user has < 10 assigned cases, fires a second `/api/cases` call for unassigned fill, mixing ownership contexts in one list. | `WorklistMini.tsx:53–65` |
