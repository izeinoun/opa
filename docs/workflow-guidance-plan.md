# Plan: Workflow-Guidance UX for the Analyst (PayGuard app + Assistant)

This plan adds UI/UX that guides an analyst (and supervisor) through the case
lifecycle described in [`analyst-supervisor-workflow.md`](./analyst-supervisor-workflow.md),
across **both** surfaces:

1. **PayGuard** — the React case-management app (`client/`).
2. **The Assistant** — the chat that dynamically generates UI via `present_view`
   directives and HTML cards (`server/app/services/assistant/`, `client/src/components/assistant/`).

---

## The central idea: one shared "Case Guidance Engine"

Both surfaces need the same thing — *given a case, what step is it on, what's
done, what's blocked, and what should the analyst do next.* Today neither has it:

- **PayGuard app:** status is shown only as a flat `StatusBadge`; there is no
  stepper or progress indicator. The lifecycle is implicit in `VALID_TRANSITIONS`
  and the status-gated buttons in `CaseActions.tsx`.
- **Assistant:** read-only navigation + Q&A. The `present_view` `directive` event
  isn't even handled on the client yet (`handleEvent` in `AssistantPanel.tsx` has
  no `directive` branch), and the agent has no notion of case lifecycle state.

So the foundation is a **single backend service** that computes lifecycle +
next-action, consumed by both. It encodes the exact gates from the workflow doc
(the DET-09 `needs_review` hard block and the high-dollar supervisor gate). The
engine itself needs **no schema change / migration** — it's pure computation over
existing case, finding, and amount-at-risk data.

---

## Part 1 — Backend: Case Guidance Engine (new, shared)

**New file:** `server/app/services/case_guidance_service.py`
**New schema:** `server/app/schemas/guidance.py`

`compute_guidance(case, user) -> CaseGuidance` returns:

```jsonc
{
  "lifecycle": [
    {"key":"assign",          "label":"Assign",              "state":"completed"},
    {"key":"review_findings", "label":"Review findings",     "state":"current",
       "detail":"2 of 3 findings need review"},
    {"key":"submit_decision", "label":"Submit decision",     "state":"upcoming"},
    {"key":"supervisor",      "label":"Supervisor approval", "state":"upcoming","conditional":true},
    {"key":"notice",          "label":"Recoupment letter",   "state":"upcoming"},
    {"key":"recovery",        "label":"Recovery & close",    "state":"upcoming"}
  ],
  "current_step":"review_findings",
  "next_action":{
    "kind":"disposition_finding",
    "label":"Review DET-09 finding",
    "explanation":"DET-09 (LLM coding) is at 0.72 confidence and must be accepted, rejected, or adjusted before a recoupment letter can be sent.",
    "target":{"view":"case","params":{"case_id":123,"tab":"findings","finding_id":"…"}}
  },
  "blockers":[{"type":"needs_review","count":2,"message":"2 findings need analyst review"}],
  "remaining_summary":"Resolve 2 findings → submit decision → supervisor approval ($4,200 > threshold) → letter → recovery.",
  "role_context":{"is_owner":true,"role":"analyst","supervisor_gate":true}
}
```

**Lifecycle steps** (analyst-centric, from the workflow doc), with a `conditional`
flag for the supervisor gate; SIU is rendered as a side-branch chip rather than a
main step:

`intake/837 → assign → review_findings → submit_decision → (supervisor) → notice → recovery/close`

**Step-state computation:** map `case.status` to a step index; earlier steps
`completed`, current `current`, later `upcoming`. The `supervisor` step is marked
`conditional` and rendered "skipped" when `amount_at_risk ≤ threshold`. A
supervisor reject (`pending_supervisor → in_review`) naturally recomputes to
"returned for rework."

**Next-action rules** (priority-ordered, encoding the doc's gates):

| Case state | next_action |
|---|---|
| `awaiting_837` | Link 837 / adjudicate without it |
| `new`, viewer ≠ owner | Take ownership |
| `new`/`assigned`, owner | Start review |
| `in_review` **and** any `needs_review` finding | **Review {DET-XX} finding** (the blocker — pick highest-confidence `needs_review`) |
| `in_review`, none `needs_review` | Submit a decision (+ "will need supervisor approval" if at-risk > threshold) |
| `pending_supervisor`, viewer = supervisor | Approve or reject |
| `pending_supervisor`, viewer = analyst | Awaiting supervisor (no action) |
| `notice_sent`/`provider_responded`/`reconciling` | Record recovery |
| terminal `closed_*` | Case closed (none) |

**Endpoint + embed:**
- `GET /api/cases/{id}/guidance` in `routes/cases.py` (for the assistant's
  in-process tool call).
- Also **embed `guidance` in the existing `CaseDetail` response** so the app gets
  it without a second round-trip. Reuse `amount_at_risk`
  (`services/amount_at_risk.py`), the threshold setting (see Part 5), and
  `suggested_decision` (already computed) inside the engine.

---

## Part 2 — PayGuard app (React) changes

**A. `CaseLifecycleRail.tsx` (new)** — vertical stepper on `CaseDetailPage`,
driven by `caseDetail.guidance.lifecycle`. Completed (✓ green), current (pink
`#FE017D` highlight), blocked (amber), upcoming (gray) — reusing the status-color
palette from `priorityUtils`/`designSystem`. Slim left rail on the case page (or
atop the existing right rail). This is the persistent "where am I" indicator the
page lacks today.

**B. `NextActionCard.tsx` (new)** — prominent card at the top of the right rail,
above `CaseActions`. Shows `guidance.next_action.label` + one-sentence
`explanation` + a CTA button that performs the in-app action (e.g., "Review
DET-09" switches to the findings tab and highlights the blocking finding; "Submit
a decision" opens `CloseCaseModal`). Generalizes the existing
`SuggestedDecisionBanner` from decision-only to *every* step.

**C. Remaining-steps caption** — render `guidance.remaining_summary` as a muted
one-liner under the case header.

**D. Wiring:** add `guidance` to the `CaseDetail` type (`types/index.ts`) and
consume via the existing `getCase`/React Query hook — no new service call.

---

## Part 3 — Assistant backend changes

**A. New read tool `get_case_guidance(case_id)`** in
`services/assistant/tools.py` → maps to `GET /api/cases/{id}/guidance`. Lets the
model reason about next steps in prose.

**B. Auto-attach guidance deterministically.** In `agent.py`, when a turn
resolves to a case (a `present_view` `case` directive, or the conversation is
about a specific case), call the guidance engine server-side and attach it to the
emitted events:
- add `context: {case_id, guidance}` to the `directive` event, and
- add `guidance` + `remaining_summary` fields to the `final` event.

Doing this deterministically (rather than relying on the LLM to format it) keeps
the "Next" button and the remaining-steps sentence **grounded in real case
state** — no hallucinated steps.

**C. Prompt update** (`prompt.py`): when the conversation concerns a case, the
model's prose body stays conversational, but it defers the next-step /
remaining-steps chrome to the injected structured fields (no duplicated or
inconsistent guidance text).

---

## Part 4 — Assistant frontend changes

**A. Handle the `directive` event (prerequisite).** Add a `case 'directive'`
branch to `handleEvent` in `AssistantPanel.tsx`. This is the missing link that
makes the "cockpit" real.

**B. Two-column layout (example *a*).** Restructure `AssistantPanel` from one
chat column into:
- **Left "Workflow" column (~280px):** renders the **shared `CaseLifecycleRail`**
  (same component as Part 2) when a case is in context — fed by
  `event.context.guidance` — with in-play/completed steps highlighted. When no
  case is in context, show the generic analyst day-flow (worklist → review →
  decision → letter → recovery) or worklist stage counts (via the existing
  `get_my_dashboard`/`search_cases` tools).
- **Right column:** the existing chat. Collapse the left rail on narrow widths.

**C. "Next" pill (example *b*, part 1).** After a case-related response, render a
`Next → {label}` button from `final.guidance.next_action`, with `explanation` as
subtext/tooltip. Clicking it routes to the action (see Amendment 2).

**D. Bottom-of-response remaining-steps sentence (example *b*, part 2).** Render
`final.remaining_summary` as a muted line beneath the assistant message —
grounded, not model-authored.

---

## Part 5 — Shared component strategy

`CaseLifecycleRail` and the `CaseGuidance` TypeScript type are authored once and
imported by both the PayGuard pages and the assistant panel. Put the rail + types
in a neutral location (`client/src/components/workflow/` and
`types/guidance.ts`) so both consume the same code and styling.

---

# Amendment 1 — Externalize the high-dollar threshold to `.env`

This **resolves Gap #1** in the workflow doc (which currently notes the threshold
is hardcoded and the config key is unused).

- **`server/app/config.py`:** add `high_dollar_threshold: float = 2000.0`, sourced
  from env var `HIGH_DOLLAR_THRESHOLD` (the pydantic `Settings` already backs the
  other env holders).
- **`server/app/services/case_service.py`:** delete the
  `SUPERVISOR_THRESHOLD = 2000.0` / `SUPERVISOR_AMOUNT_GATE = 2000.0` constants and
  read `settings.high_dollar_threshold` at the gate.
- **Guidance engine (Part 1):** reads the *same* `settings.high_dollar_threshold`,
  so the UI's "will need supervisor approval" hint can never disagree with what the
  backend enforces — one source of truth.
- **Housekeeping:** add `HIGH_DOLLAR_THRESHOLD=2000` to `.env.example`, surface it
  in `verify_env.py`, and update Gap #1 in `analyst-supervisor-workflow.md`.

> Uses `.env` (process-level config), not the per-deploy `runtime_config` table.
> If it ever needs runtime tunability without redeploy, the engine is the single
> place to swap the source.

---

# Amendment 2 — Assistant can perform **writes**, with chat-agent confirmation

The assistant becomes action-capable through both a text prompt and a click in the
cockpit card — but **every mutation passes through a mandatory confirmation gate in
the chat.**

**A. Write tools** — add to `services/assistant/tools.py`, mapped to existing
mutation endpoints (so all server-side RBAC + gates + audit logging apply
unchanged): `assign_case` / `take_ownership`, `transition_case`,
`accept_finding`, `reject_finding`, `adjust_finding`, `escalate_to_supervisor`,
`approve_case` / `reject_case` (supervisor), `record_recovery`,
`escalate_to_siu`.

**B. Confirmation gate** — new special tool `confirm_action`, modeled on the
existing `ask_user`/`awaiting_user` pattern:
1. Model decides to write → calls `confirm_action` with a human-readable summary +
   the concrete `{tool, input}` it intends to run.
2. Backend emits a new `awaiting_confirmation` event (summary + diff-style "what
   will change", e.g., *"Accept DET-09 finding on OPA-2026-00123 → at-risk
   recomputes to $4,200; case becomes eligible to submit a decision."*).
3. Frontend renders **Confirm / Cancel** buttons in the chat (reusing the
   disambiguation-button UI already in `AssistantPanel`).
4. On Confirm, the client sends a `tool_result` continuation; the agent calls the
   real write tool, executes in-process as the user, and **re-emits the case
   `directive` + fresh `guidance`** so the cockpit lifecycle rail advances live.
5. Mutations are **never** executed without an explicit confirm — write tools
   refuse to run unless reached via a confirmed `confirm_action`.

**C. Two entry points:**
- **Text prompt:** "accept the DET-09 finding" → agent proposes → user confirms.
- **Click in the cockpit card:** the `NextActionCard` / `CaseLifecycleRail`
  buttons (and per-finding actions) in the assistant's left column become
  interactive. A click doesn't mutate directly — it emits a *structured proposed
  write* that the agent echoes back as a confirmation in chat, then executes on
  Confirm.

**D. Safety / consistency:** supervisor-only actions (approve/reject, reassign)
still hard-fail server-side for analysts and surface as a clear chat error; the
DET-09 `needs_review` block and the high-dollar gate are enforced on the same
endpoints, so the assistant cannot route around them. Every write produces a
normal `audit_logs` entry.

---

# Amendment 3 — Keep the displayed case in chat context

**Root cause of the observed bug:** the model's only context is the `messages`
array. The case shown in the cockpit (or the case page the assistant was opened
from) is never injected, so at the start of a session "the displayed case"
resolves to nothing.

**Fix — an active-case context channel:**
- **`ChatRequest`** (`routes/assistant.py`) gains an optional
  `context: {active_case_id?, active_view?}`.
- **Frontend** maintains `activeCase` state and sends it on every turn. Set two
  ways: (1) when a `directive` mounts a case in the cockpit, and (2) **seeded on
  panel-open from the current route** — open the assistant on `/cases/123` and
  `active_case_id = 123` immediately, before any message. This is the
  start-of-session gap.
- **Backend** injects a short context preamble into the system prompt / leading
  message ("The user is currently viewing case OPA-2026-00123."), and uses
  `active_case_id` as the default for the fast-path and `present_view` when the
  user says "this case" / "the displayed case." It also lets the agent fetch
  `get_case_guidance(active_case_id)` without asking which case.
- Context persists for the session and updates whenever the cockpit case changes.

---

## Sequencing

1. **Threshold → `.env`** (Amendment 1) — tiny, and the guidance engine depends on it.
2. **Case Guidance Engine** (Part 1).
3. **PayGuard lifecycle rail + NextActionCard** (Part 2).
4. **Active-case context channel** (Amendment 3) — small, fixes the known bug;
   writes/cockpit clicks depend on the agent reliably knowing the case.
5. **Assistant `directive` handling + two-column cockpit** (Part 4 + Part 3).
6. **Assistant write tools + confirmation gate** (Amendment 2) — last; builds on 4 & 5.

## Risks / call-outs

- The threshold must be read from `settings.high_dollar_threshold` in both the
  enforcement path and the guidance engine so the UI never disagrees with what is
  enforced.
- Keep the confirmation gate mandatory: never execute an assistant mutation
  without an explicit `awaiting_confirmation` → Confirm round-trip.
- Server-side RBAC and the `needs_review` / high-dollar gates remain the source of
  truth; assistant tools call the same endpoints and cannot bypass them.
- The two-column assistant panel must stay responsive (panel is 840px / 95vw) —
  collapse the left rail on narrow widths.
