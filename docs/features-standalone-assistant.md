# The Standalone Assistant — Features & Capabilities

**What it is:** a single conversational surface that behaves like a full application. You
talk to it in plain language; it answers, and — when useful — it *mounts live,
interactive views* (a "cockpit"), offers *one‑click action pills*, and executes
work on your behalf through a human‑confirmed gate. It federates data and actions
across the whole suite: **PayGuard** (post‑pay), **ClaimGuard** (pre‑pay), **SIU**,
and **ClearLink** (member clinical data) — from one chat box.

> Dev port `5179`; in production it runs against the OPA backend at `payguard.penguinai.studio`. Auth is cookie‑based; every capability is gated by your role and app access.

---

## 1. Why it's not "just a chatbot"

A normal chatbot returns text. The Standalone Assistant returns **an application experience**:

- It **renders working views inline** — a case cockpit, a worklist, your dashboard, a daily briefing — with real data and real buttons, not a paragraph describing them.
- It offers **smart action pills** — the next best actions for the thing you're looking at, wired to real endpoints.
- It **acts** — take ownership, record a decision, generate a notice, email a provider — but only after **you confirm**. The principle is explicit: *the human clicks; the model never mutates on its own.*
- It **remembers what you're looking at** — the mounted view feeds context back so "this case" and "this member" resolve correctly.
- It pulls **clinical truth from ClearLink** (diagnoses, meds, labs, prior auths, SDOH, RAF/PCMH explanations) alongside claim data — a genuine 360° view.

---

## 2. Architecture at a glance

```
 You ──▶ Assistant SPA ──SSE──▶ OPA Assistant agent ──▶ Anthropic (fast model)
   ▲         (cockpit,            (tool-use loop)        │
   │          pills, gate)                               ├─▶ OPA REST (in-process): PayGuard / ClaimGuard / SIU
   └───── live views ◀── directives ─────────────────────┤
                                                         └─▶ ClearLink MCP (HTTP, X-API-Key): clinical tools
```

- **One streaming endpoint** — the SPA POSTs to `/api/assistant/chat/stream` and consumes **Server‑Sent Events**. Event types: `assistant_text`, `tool_start`/`tool_end`, `directive` (mount a view), `awaiting_user` (option chips), `awaiting_confirmation` (write gate), `final` (+ follow‑up chips), `error`.
- **Model tier:** the **fast** model (`ANTHROPIC_MODEL_FAST`, Haiku), for low‑latency conversation and tool use. The heavier Sonnet tier is reserved for deep audit/document work elsewhere.
- **Tool‑use loop:** a bounded manual loop (≤8 iterations) with prompt caching and context trimming, so long sessions stay fast and cheap.
- **Identity & governance:** the agent calls OPA's own API **in‑process** as *you* (forwards your user id), so server‑side **RBAC, workflow gates, and audit logging apply to everything** — the assistant is not a backdoor.
- **Tool federation:** OPA‑native tools run in‑process; ClearLink tools are called over its **MCP** interface. ClearLink's tools are **discovered dynamically**, so new clinical capabilities appear in the assistant without code changes.

---

## 3. The Cockpit — a dynamic, app‑like view surface

The cockpit is the assistant's superpower. When the model decides a view beats prose,
it emits a `directive` and the SPA **mounts a real component inline** in the
conversation. Views available:

| View | What it shows |
|---|---|
| **case** | The full **Case Cockpit** (see below) |
| **worklist** | A compact, paginated case table (scope: mine / unassigned / all; filter by status, priority, overdue) — click a row to open its cockpit |
| **my_dashboard** | Personal productivity: stat tiles + pipeline snapshot (week / month / quarter) |
| **briefing** | A full daily briefing: your stats, trends, you‑vs‑team bars, and priority queue |

**The Case Cockpit** is a self‑contained case application rendered *in the chat*:

- **Header** — case number, status pill, assignee, a plain‑language summary, and a deep link to the full PayGuard case.
- **Amount at risk** and a **suggested‑decision banner** (recommendation + confidence % + reason).
- **Workflow lifecycle rail** — the case's stages and where it is now, driven by the backend guidance engine (no need for the model to re‑explain the process).
- **Case‑level action pills** (§5) and, per finding, **Approve / Deny / Edit‑amount** pills.
- **Tabbed detail:** Overview (interactive findings), Notes, Evidence, Disputes, 835/ERA, Output/notices.

**It updates dynamically as the conversation flows.** A directive from the agent, a
Launchpad button, or a worklist row all set the active view; after any write the
cockpit **auto‑refreshes** (query invalidation) so what you see always reflects the
latest state. The mounted view also becomes **conversational context** — so you can
say "take this one" and the assistant knows which case you mean.

A **deterministic fast‑path** short‑circuits obvious navigation ("open case 142",
"my cases", "my dashboard") straight to a view without an LLM round‑trip — instant.

---

## 4. Prebuilt & structured surfaces ("forms")

The assistant favors **structured, prefilled interactions** over free‑text wherever a
decision or value is needed:

- **The confirm‑action card (write gate).** Any mutation is proposed as a prefilled
  card: the action, its parameters, and a deterministic **"what will change" preview**,
  with **Confirm / Cancel**. Nothing is written until you confirm — and on confirm the
  write executes deterministically (no extra model round‑trip). This is the assistant's
  core "form": a review‑before‑commit surface for every state change.
- **Option chips (`ask_user`).** When the assistant needs a choice (e.g. *what should
  the provider message focus on?*), it renders 2–4 **soft‑button options** instead of
  making you type.
- **In‑cockpit forms.** The Case Cockpit hosts real forms: an **add‑note** box (persists
  to the case) and a **PDF drag‑drop evidence upload** that auto‑triggers AI
  evidence validation against the claim.
- **Chat‑captured structured input.** When a pill needs a number or reason (e.g. "edit
  amount", "reason for rejection"), the assistant captures it through the chat box with
  **client‑side validation** (amount ≤ claim total, non‑empty reason) before acting.

> Scope note: the Standalone Assistant does not create claims/cases from scratch — case creation is handled by the intake pipeline. The assistant's structured surfaces are for **reviewing, deciding, annotating, and acting on** existing work.

---

## 5. Smart action pills

Pills turn "what should I do next" into one click. They are **guidance‑driven** (the
backend computes the valid, recommended next actions for the exact case state) and
**human‑in‑the‑loop**.

- **Case‑level pills** (from the guidance engine): take ownership, start review,
  adjudicate without 837, approve recoverable, set not‑recoverable, generate/send
  notice, supervisor approve/reject, escalate, send to SIU, reopen, record recovery.
  Each pill carries a style (primary / default / caution), an **enabled/disabled state
  with a reason**, and a **recommended** flag. **Irreversible actions** (send notice,
  supervisor approve) arm an inline **Confirm/Cancel** step before firing.
- **Finding‑level pills:** Approve / Deny / Edit‑amount on each finding row (shown only
  while the case is actionable).
- **Follow‑up chips:** after every reply the assistant suggests 2–4 next‑step chips.
- **Quick‑action chips & Launchpad:** role‑aware shortcuts with **live counts** pinned
  at the top (e.g. my open cases, overdue), plus context chips when a case is open
  (contact provider, escalate, show working case, view member record).

Every pill routes through one handler that either executes immediately or first
collects the required input — always ending at the confirm gate for writes.

---

## 6. Tools & capabilities (the assistant's toolbox)

The agent exposes a governed set of tools. **Read** tools answer questions; **write**
actions only run through the confirm gate; **control** tools drive the UI. Availability
is filtered by your app access (PayGuard / ClaimGuard / SIU); ClearLink tools are open
to any authenticated user.

### 6.1 Control / UX tools
| Tool | Purpose |
|---|---|
| `present_view` | Mount a cockpit view (worklist / case / my_dashboard) |
| `ask_user` | Ask a disambiguating question with option chips |
| `confirm_action` | Propose a write; render the confirm‑gate card |

### 6.2 PayGuard (post‑pay) — read
`search_cases` (worklist search by status/priority/LOB/detector/assignee/overdue/…),
`get_case`, `get_case_guidance` (what's next), `get_case_notes`,
`get_payguard_dashboard` (KPIs, aging, recovery trend), `get_daily_briefing`,
`list_provider_risk` (ML risk explanations — supervisor/admin).

### 6.3 ClaimGuard (pre‑pay) — read
`list_prepay_claims` (by status/specialty), `get_prepay_claim`, `get_prepay_dashboard`.

### 6.4 SIU — read
`get_siu_dashboard` (FWA breakdown / investigations).

### 6.5 Cross‑app
`search_members` (resolve a member), `get_my_dashboard` (personal productivity),
**`get_member_360`** — a unified member profile spanning **PayGuard + ClaimGuard + ClearLink**.

### 6.6 Write actions (only via the confirm gate)
`take_ownership`, `assign_case`, `transition_case`, `approve_case`, `reject_case`,
`escalate_to_supervisor`, `accept_finding` / `reject_finding` / `adjust_finding`,
`generate_provider_notice`, `reevaluate_rules`, `send_notice_to_provider`,
`send_provider_inquiry`. Each executes as *you*, subject to RBAC, the high‑dollar
approval gate, and audit logging.

### 6.7 ClearLink clinical tools (via MCP)
The assistant reaches ClearLink's member clinical system over MCP. ClearLink defines its
tools as data (an `agent_tools` registry) and the assistant **discovers them
dynamically**, so the full set is available and can grow without code changes. The
current inventory:

| Tool | Purpose |
|---|---|
| `search_members` | Fuzzy member lookup by name/ID (LLM matcher — handles typos, partials, reversed order) |
| `get_member_demographics` | Demographics + PCP, plan, status, **RAF score & risk level** |
| `list_diagnoses` | ICD‑10 list with HCC codes and RAF weights (active/inactive, since date) |
| `add_diagnosis` | Add a validated ICD‑10 to a member (dedupe‑checked) — a write |
| `list_medications` | Medications (dose, frequency, prescriber, status) |
| `list_prior_authorizations` | PA requests (provider, CPT, urgency, status, decision) |
| `list_dates_of_service` | Visits/encounters (facility, type, primary dx) to scope questions |
| `get_claims_window` | Claims overlapping a date range (charges/paid, provider, dx) |
| `get_labs_window` | Lab results in a date range (value, unit, reference range, status) |
| `get_provider_messages` | Secure messages with the member's providers |
| `get_socioeconomic_profile` | SDOH profile (housing, food, transport, language, risks) |
| `explain_pcmh_tier` | Why a member is at their PCMH tier — rules, triggering dx, RAF breakdown |

> Member‑scoped ClearLink tools take the member's **MRN / member number** (not an internal UUID); ClearLink resolves it internally. `search_members` first turns a name into that MRN.

---

## 7. APIs & integration

| Integration | How | Auth |
|---|---|---|
| **Anthropic API** | The agent's single LLM call site (fast model tier) | `ANTHROPIC_API_KEY` |
| **OPA REST (PayGuard/ClaimGuard/SIU)** | Called **in‑process** (ASGI) as the signed‑in user; all reads + all writes | forwarded user identity → server RBAC/gates/audit |
| **ClearLink MCP** | `tools/list` + `tools/call` over JSON‑RPC/HTTP at `CLEARLINK_MCP_URL` (`:8010/mcp`) | `X-API-Key` (`CLEARLINK_MCP_API_KEY`) |

The SPA itself calls the assistant stream endpoint plus a handful of REST endpoints for
the cockpit (case detail, notes, documents, evidence validation, findings decisions,
case transitions/approvals, SIU escalation). Cross‑app navigation uses deep links to the
underlying apps. ClearLink integration **fails soft** — if the MCP key is unset or
ClearLink is unreachable, clinical tools are simply skipped; everything else keeps working.

---

## 8. Safety, governance & resilience

- **Human‑in‑the‑loop writes.** No mutation happens without an explicit Confirm on a
  preview card. The model proposes; the person disposes.
- **RBAC everywhere.** Tools are filtered to your apps; the in‑process calls run as you,
  so a user can never do through the assistant what they can't do in the app.
- **Audit trail.** Every write goes through the normal audited endpoints.
- **High‑dollar gate.** Terminal decisions above the configured threshold route to
  supervisor approval — the assistant respects the same gate as the UI.
- **Deterministic first.** Navigation fast‑paths and the confirm‑gate execution are
  deterministic; the LLM is used for understanding and drafting, not for the final write.
- **Fail‑soft federation.** ClearLink outages degrade gracefully; context trimming keeps
  long conversations responsive.

---

## 9. What it looks like in practice

- **"Show me my highest‑priority case and take it."** → cockpit mounts the case; the
  assistant highlights the recommendation; you click **Take ownership** → confirm →
  the cockpit refreshes with you as owner.
- **"Why is this member's RAF so high?"** → `explain_pcmh_tier` + `list_diagnoses`
  (ClearLink) → a plain‑language breakdown of the HCCs driving the score.
- **"Email the provider about the missing documentation."** → the assistant proposes
  a focus (option chips) → drafts the message → **confirm gate** → secure inquiry sent,
  audited.
- **"Give me a 360 on member Ostrowski."** → `get_member_360` stitches PayGuard cases,
  ClaimGuard claims, and ClearLink clinical data into one profile.
- **"Open case 142."** → instant cockpit (deterministic fast‑path, no model call).

---

*In short: the Standalone Assistant is a conversational front‑door that renders working
application views, proposes guided actions, executes them under human confirmation and
full governance, and unifies claim and clinical data across PayGuard, ClaimGuard, SIU,
and ClearLink.*
