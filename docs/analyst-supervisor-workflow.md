# Day in the Life: Analyst & Supervisor Case Workflow (PayGuard / post-pay)

This document describes the **end-to-end workflow** for a PayGuard post-pay overpayment
case as it moves from the worklist through analyst review to supervisor approval and
recovery. It is written as a business narrative — what each person does and why — with
ASCII diagrams covering every branch the code can take.

It focuses on two things the team cares about most:

1. **Manual verification of rules** — which detector findings an analyst *must* review by
   hand before a case can advance (especially the LLM-touched coding detector), and which
   are auto-accepted.
2. **The $2,000 supervisor gate** — how a case above the dollar threshold is held for a
   supervisor to approve or reject before any money is pursued.

> **Scope & sourcing.** Everything below is derived from the PayGuard backend code
> (`server/app/...`), not the README or aspirational docs. Where the code differs from the
> documented intent, it is called out in a **⚠️ Gap** note. Pre-pay (ClaimGuard) AI findings
> are mentioned only where they border the PayGuard flow.

---

## Cast of characters

| Role | Seeded examples | What they can do |
|------|-----------------|------------------|
| **Analyst** | ana.chen, james.park, priya.shah, tom.rivera, lisa.nguyen, marcus.bell | Self-assign cases, review findings (accept / reject / adjust), add notes, submit a recoupment or close-without-recovery decision. |
| **Supervisor** | sarah.kim, david.osei | Everything an analyst can do, plus: assign/unassign cases to others, **approve or reject** decisions held at the $2,000 gate, reopen closed cases, bulk-assign/close. |
| **Admin** | rachel.burns | Supervisor powers plus config: letter templates, runtime config, ML training config. |
| **Intake / system bots** | data.intake, system.bot | Machine actors that ingest 835/837 files and run detectors. |

> **⚠️ Gap — roles.** The live authorization checks read the single legacy `opa_users.role`
> column (`"analyst" | "supervisor" | "admin" | ...`). A richer multi-role RBAC layer
> (`roles` / `role_apps` / `user_roles` tables) exists but is **not yet uniformly enforced** —
> it is opt-in per route. Treat the single-role column as the source of truth today.

---

## The case lifecycle at a glance

Every case carries a `status` string. There is no DB-level enum — the service layer
enforces the allowed transitions. The headline path and its branches:

```
                          ┌─────────────────┐
   835 (ERA) ingested ───►│   awaiting_837  │  (created unassigned; diagnosis-dependent
                          └────────┬────────┘   detectors deferred until the 837 links)
                                   │ 837 links diagnoses / manual override
                                   ▼
                          ┌─────────────────┐
                          │       new       │  (in the worklist, unassigned)
                          └────────┬────────┘
                       analyst self-assigns │ (or supervisor assigns)
                                   ▼
                          ┌─────────────────┐
                          │    assigned     │
                          └────────┬────────┘
                       analyst opens & works │
                                   ▼
                          ┌─────────────────┐
            ┌────────────►│    in_review    │◄───────────┐
            │             └────────┬────────┘            │
            │   analyst submits a  │  terminal decision  │ supervisor
            │   decision           │                     │ REJECTS
            │                      ▼                     │ (back to analyst)
            │        ┌─────────────────────────┐         │
            │        │  amount > $2,000  ?      │         │
            │        └───────┬───────────┬──────┘         │
            │            YES │           │ NO             │
            │                ▼           ▼                │
            │     ┌───────────────────┐  │                │
            │     │ pending_supervisor│  | (direct)       │
            │     └─────────┬─────────┘  |                │
            │     supervisor │ APPROVES ─|─────────────────┘
            │                ▼
            │   ┌────────────┴─────────────┐
            │   │ decision was…            │
            │   ▼                          ▼
            │ ┌──────────────┐   ┌────────────────────────┐
            │ │ notice_sent  │   │ closed_not_for_recoup  │ (terminal)
            │ └──────┬───────┘   └────────────────────────┘
            │        │ recoupment letter auto-generated
            │        ▼
            │ ┌──────────────────┐
            │ │ provider_responded│ (optional)
            │ └──────┬───────────┘
            │        ▼
            │ ┌──────────────┐   record recovery
            │ │  reconciling │◄──── partial ────┐
            │ └──────┬───────┘                  │
            │        │ full recovery recorded   │
            │        ▼                          │
            │ ┌──────────────────┐              │
            └─│ closed_recovered │ (terminal)   │
              └──────────────────┘              │
                                  record recovery
                                  (notice_sent / provider_responded)
```

Other terminal closures reachable by supervisor/bulk actions:
`closed_written_off`, `closed_overturned`, `closed_no_overpayment`. Any `closed_*`
status flips the case to inactive (drops off active worklists).

---

# Part 1 — A Day in the Life of the Analyst

### 1. Morning: open the worklist

The analyst starts on the **Worklist**. Overnight, the intake bots parsed 835 remittance
files: each paid claim that tripped one or more detectors became a case. New cases land as
`new` (unassigned) — or as `awaiting_837` if the claim's diagnoses haven't been linked yet,
in which case the diagnosis-dependent detectors (the coding detector, medical-necessity)
haven't run.

Each case already shows a **priority band** (HIGH / MEDIUM / LOW) and a **priority score**,
computed from the dollar amount at risk, the Bayesian posterior likelihood, and urgency
(how close the case is to its deadline). The analyst works HIGH-priority, soonest-deadline
cases first.

```
   Worklist (filterable by status, priority, assignee)
   ┌───────────────────────────────────────────────────────────┐
   │ OPA-2026-00123  HIGH    $4,200   deadline in 9d   [unassigned] │
   │ OPA-2026-00124  MEDIUM  $1,150   deadline in 21d  [unassigned] │
   │ OPA-2026-00125  HIGH    $880     deadline in 4d   [ana.chen]   │
   └───────────────────────────────────────────────────────────┘
```

### 2. Take ownership (self-assign)

The analyst clicks a `new` case and **self-assigns** it. Self-assignment is always allowed
for analysts; assigning a case to *someone else* is a supervisor/admin action. On first
assignment the case moves `new → assigned`.

```
   new ──(analyst self-assigns)──► assigned
   new ──(supervisor assigns to analyst, notifies them)──► assigned
```

### 3. Open the case and read the findings

Opening the case moves the analyst's mental state into review; submitting the first decision
or working the findings advances `assigned → in_review`. The case detail shows:

- The claim, claim lines, member, provider, and the provider's ML billing-variance score.
- Every **finding** a detector produced, each with a pre-seeded **disposition**.

The detectors and how their findings arrive pre-dispositioned:

| Detector | What it flags | Default disposition when the case is created |
|----------|---------------|----------------------------------------------|
| **DET-01** Duplicate | Same member + CPT + service date (exact = 0.95 confidence; partial overlap = 0.75) | **accepted** |
| **DET-02** Retro-eligibility | Member not enrolled / wrong line of business at service date | **accepted** |
| **DET-04** Fee schedule | Paid > allowed × 1.05 | **accepted** |
| **DET-06** NCCI / MUE | Mutually-exclusive CPT pairs, unit-limit violations | **accepted** |
| **DET-08** Excluded provider | Rendering NPI on OIG/SAM exclusion list (confidence 1.0, **hard rule**) | **accepted** |
| **DET-09** Coding errors | Invalid ICD→CPT, unbundling — **and an LLM path for UB-04 inpatient claims** | **depends on confidence — see below** |

**The key idea:** the five deterministic detectors are **auto-accepted** at creation. The
analyst can still override any of them (reject a false positive, adjust a dollar amount), but
nothing *forces* them to. The detector that *forces* manual verification is **DET-09**.

### 4. Manual verification — the DET-09 / LLM gate

DET-09 is the only detector routed as an "LLM detector." It has a hybrid implementation:

- **CMS-1500 / outpatient claims** → deterministic ICD→CPT mismatch + unbundling lookups.
- **UB-04 inpatient claims** → each code is evaluated by the **LLM**, which returns a
  retain/deny judgment and a confidence (with a deterministic fallback if the LLM call
  fails).

Because DET-09 output can be model-generated, its findings are **confidence-gated** into a
disposition the moment the case is created:

```
   DET-09 finding confidence
   ───────────────────────────────────────────────────────────
   confidence ≥ 0.85   ──►  accepted      (high — trust it, counts toward $ at risk)
   0.65 ≤ conf < 0.85  ──►  needs_review  (★ analyst MUST decide — BLOCKS the case)
   confidence < 0.65   ──►  rejected      (low — auto-dismissed, $0)
```

A finding in **`needs_review` is a hard block.** The case cannot advance to a recoupment
letter while any finding sits in `needs_review`; the transition is refused with *"One or more
findings need analyst review (accept or reject) before a recoupment letter can be sent."*

So the analyst's core verification job is: **resolve every `needs_review` finding.** For each
one they read the rationale (and, for UB-04, the LLM's per-code reasoning), check it against
the claim, and choose one of three actions:

```
   needs_review finding ──► [ ACCEPT ]  valid overpayment → counts at its original amount
                       ├──► [ REJECT ]  false positive   → contributes $0 (reason required)
                       └──► [ ADJUST ]  partly valid      → counts at an analyst-set amount
                                                            (new amount + reason required)
```

Accepting / rejecting / adjusting records *who* decided and *when* on the disposition, and
immediately **recomputes the case's amount at risk**.

> **How the dollar amount at risk is computed.** Each claim line is attributed to the single
> **highest-priority** detector that flagged it (rank order DET-08 > DET-01 > DET-02 > DET-04
> > DET-06 > DET-09) so overlapping findings never double-count. A `rejected` or
> `needs_review` finding contributes **$0**; an `adjusted` one contributes the analyst's
> amount; an `accepted` one contributes its original amount. This deduped total is what the
> $2,000 gate later tests against.

> **⚠️ Gap — AI/LLM findings vs. PayGuard cases.** A separate AI service produces
> `CG-BASIC-V1` findings with **NULL confidence and NULL dollar amount**. These belong to the
> **pre-pay (ClaimGuard)** flow, where a specialist accepts/rejects them to build a provider
> correction letter — they are *not* wired into the post-pay case disposition/at-risk path.
> In PayGuard post-pay, the "LLM rule that a human must check" is specifically **DET-09's
> `needs_review` findings**, not `CG-BASIC-V1`.

### 5. Note the work

Throughout, the analyst adds **case notes** — append-only free-text commentary (supports
`@mentions`, which notify the mentioned user). Notes are distinct from the **audit log**,
which records every state change automatically (who moved the case, from which status to
which, when).

### 6. Special case: an excluded provider (DET-08)

If **DET-08** fired, the posterior likelihood is hard-overridden to 0.98 — the provider is on
an exclusion list, which is close to a certainty of overpayment. Practically, the analyst
treats this as near-certain recovery, and these often warrant a **fraud referral**:

```
   DET-08 present ──► analyst may escalate to SIU (fraud/waste/abuse investigation)
                      POST /api/siu/escalate  → case is "siu_frozen" (evidence read-only)
```

> SIU escalation is a *different* mechanism from the $2,000 supervisor approval gate. SIU =
> "this looks like fraud, investigate it." The $2,000 gate = "this is a high-dollar recovery
> decision, a supervisor must sign off." A case can hit either, both, or neither.

### 7. Submit the decision

Once every finding is dispositioned (nothing left in `needs_review`), the analyst submits a
**terminal decision** on the case:

- **Recoup** — pursue recovery. Target status `notice_sent`.
- **Close, not for recoupment** — drop it (e.g., findings didn't hold up). Target status
  `closed_not_for_recoup` (reason required).

The system also shows a **suggested decision** to guide the analyst: high posterior → recoup;
low posterior → not-for-recoup; middling → review further. For high-dollar cases the
suggestion explicitly reads *"high-dollar — supervisor approval required."*

What happens on submit depends entirely on the **amount at risk**:

```
   analyst submits terminal decision (recoup OR not-for-recoup)
                         │
              ┌──────────┴───────────┐
              │ amount at risk > $2,000?
              └──────────┬───────────┘
                 NO      │      YES
          ┌──────────────┘      └──────────────┐
          ▼                                     ▼
   decision executes immediately       case is HELD: status → pending_supervisor
   ┌───────────────────────────┐       the decision (recoup / not-for-recoup,
   │ recoup → notice_sent       │       reason, recovered amount, who submitted,
   │   (letter auto-generated)  │       when) is stashed in decision_metadata;
   │ not-for-recoup →           │       all supervisors are notified
   │   closed_not_for_recoup    │       ("approval_requested")
   └───────────────────────────┘                  │
                                                    ▼
                                          (handed to Part 2 — the supervisor)
```

For a **sub-$2,000** case the analyst's day on this case ends here: if they chose recoup, the
recoupment letter is generated automatically and the case is now `notice_sent`; if they chose
not-for-recoup, it's closed.

For an **over-$2,000** case, the analyst's case is now **locked** in `pending_supervisor` —
while it sits there, only a supervisor/admin can write to it. The analyst moves on to the
next worklist item and waits for the approve/reject notification.

> **⚠️ Gap — the $2,000 threshold is hardcoded.** The gate value is the constant
> `SUPERVISOR_THRESHOLD = 2000.0` (and a sibling `SUPERVISOR_AMOUNT_GATE = 2000.0`) in
> `case_service.py`. The `high_dollar_threshold` **runtime-config key referenced in the
> project docs is NOT read anywhere in the live code** — changing it has no effect today.
> Treat `$2,000` as a code constant; if it needs to be operator-tunable, wiring it to
> `runtime_config` is outstanding work.

---

# Part 2 — A Day in the Life of the Supervisor

### 1. Morning: the approvals queue

The supervisor opens their **Approvals** view, which lists every case currently in
`pending_supervisor`. Each row summarizes what the analyst is asking to do and why:

```
   Pending Supervisor Approvals
   ┌──────────────────────────────────────────────────────────────────────┐
   │ OPA-2026-00123  $4,200  recoup           by james.park  2h ago         │
   │ OPA-2026-00131  $9,750  recoup           by ana.chen    5h ago         │
   │ OPA-2026-00140  $2,300  not-for-recoup   by tom.rivera  1d ago         │
   └──────────────────────────────────────────────────────────────────────┘
```

The supervisor also has views for **workload/assignments** (to rebalance analysts) and
**SIU escalations** (active fraud referrals) — separate from this approvals queue.

### 2. Review the held decision

The supervisor opens a pending case. Because it's `pending_supervisor`, they have write
access (the analyst does not, while it's held). They review:

- The findings and their dispositions (what the analyst accepted / rejected / adjusted).
- The **stashed decision metadata** — the proposed disposition, the analyst's reason, the
  amount, and who submitted it.
- Case notes and the audit trail.

This is the second line of defense on **manual rule verification**: the supervisor is
re-checking the analyst's judgment on the findings — particularly any DET-09 / LLM-derived
findings the analyst accepted or adjusted, and the dollar amount being pursued — before real
money moves.

### 3. Decide: approve or reject

```
                 ┌─────────────────────┐
                 │  pending_supervisor │
                 └──────────┬──────────┘
              ┌─────────────┴──────────────┐
        APPROVE                         REJECT (reason required)
              │                             │
              ▼                             ▼
   execute the stashed decision      status → in_review
   ┌──────────────────────────┐      decision_metadata cleared
   │ was "recoup":            │      submitting analyst is notified
   │   → notice_sent          │      analyst revises & resubmits
   │   → recoupment letter     │      (loops back to Part 1, step 7)
   │     auto-generated        │
   │ was "not-for-recoup":     │
   │   → closed_not_for_recoup │
   └──────────────────────────┘
```

- **Approve** → the held decision executes exactly as the analyst proposed. If it was a
  recoup, the case moves to `notice_sent` **and the recoupment letter is generated
  automatically** (idempotent — it won't duplicate an existing notice). If it was
  not-for-recoup, the case closes.
- **Reject** (reason mandatory) → the case returns to `in_review`, the stashed decision is
  discarded, and the original analyst is notified to revise and resubmit. The case re-enters
  the analyst's worklist.

Every approve/reject writes an audit-log entry (`SUPERVISOR_APPROVED` /
`SUPERVISOR_REJECTED`), preserving accountability for who authorized the money.

### 4. After approval: the recovery letter and recoupment

Once a recoup decision is approved (or a sub-$2,000 recoup auto-executed), the provider notice
exists and the case is `notice_sent`. From here recovery is tracked:

```
   notice_sent
      │  provider replies (optional) ──► provider_responded
      ▼
   record a recovery (check / EFT / adjustment / credit balance / other)
      │
      ├── total recovered ≥ overpayment ──► closed_recovered  (terminal)
      └── partial                        ──► reconciling ──(more recoveries)──► closed_recovered
```

Recording recoveries can be done from `notice_sent`, `provider_responded`, or `reconciling`.
Each recovery is summed; when the running total reaches the overpayment amount the case
auto-closes as `closed_recovered`.

> **⚠️ Gap — letter issuance is not role-gated at the endpoint.** Auto-generation on approval
> is the intended path, but the underlying "send notice" endpoint itself has **no role check**
> — any authenticated caller could compose/send a notice directly, and doing so will
> auto-advance an `in_review` case to `notice_sent`, bypassing the $2,000 gate. The gate is
> enforced on the **decision-submission transition**, not on the letter endpoint. If tight
> control is required, gating the notice endpoint is outstanding work.

### 5. Reopening (exception path)

A supervisor can **reopen** a closed case (e.g., new information arrives), returning it to
`assigned` so an analyst can rework it. This is supervisor/admin-only.

---

## Worked example: the $4,200 UB-04 case

Putting it together, following a single high-dollar case with an LLM-derived finding:

```
1. Intake bot parses an 835 → claim tripped DET-04 (fee schedule) and DET-09 (coding).
   Case OPA-2026-00123 created, HIGH priority, $4,200 at risk, status = new.

2. Analyst james.park self-assigns it.                         new → assigned

3. He opens it. DET-04 finding is auto-accepted. The DET-09 finding came from the
   UB-04 inpatient LLM path at confidence 0.72 → it sits in needs_review and BLOCKS
   the case.                                                   assigned → in_review

4. James reads the LLM's per-code reasoning, agrees the coding is wrong but the dollar
   amount is high → he ADJUSTS it down with a reason. needs_review cleared; amount at
   risk recomputed to $4,200.

5. He submits a RECOUP decision. Amount > $2,000 → case is HELD.
                                                               in_review → pending_supervisor
   Supervisors notified. James moves to his next case.

6. Supervisor sarah.kim opens the approvals queue, reviews James's dispositions
   (especially the adjusted LLM finding) and the $4,200 figure.

7a. She APPROVES → notice_sent, recoupment letter auto-generated.
                                                               pending_supervisor → notice_sent
    Provider pays $4,200 by EFT → recovery recorded → closed_recovered.

7b. (Alternate) She REJECTS with a reason → back to in_review, James notified to revise.
                                                               pending_supervisor → in_review
```

---

## Quick reference — who does what, and the gates

| Step | Actor | Status change | Mandatory verification / gate |
|------|-------|---------------|-------------------------------|
| Self-assign | Analyst | `new → assigned` | — |
| Resolve `needs_review` (DET-09/LLM) | Analyst | (within `in_review`) | **Hard block** — must accept/reject/adjust every one |
| Accept/reject/adjust deterministic findings | Analyst | (within `in_review`) | Optional override; auto-accepted otherwise |
| Submit decision, ≤ $2,000 | Analyst | `in_review → notice_sent` / `closed_not_for_recoup` | Executes immediately |
| Submit decision, > $2,000 | Analyst | `in_review → pending_supervisor` | **$2,000 gate** — held for supervisor |
| Approve | Supervisor | `pending_supervisor → notice_sent` / `closed_not_for_recoup` | Re-verifies findings & amount; letter auto-generated on recoup |
| Reject | Supervisor | `pending_supervisor → in_review` | Reason required; analyst reworks |
| Record recovery | Analyst/Supervisor | `notice_sent → reconciling → closed_recovered` | Auto-closes when fully recovered |
| Reopen | Supervisor | `closed_* → assigned` | Supervisor/admin only |
| SIU escalate (fraud) | Analyst | (freezes evidence) | Separate from the $2,000 gate |

---

## Gaps & caveats summary (code vs. documented intent)

1. **$2,000 threshold is hardcoded** (`SUPERVISOR_THRESHOLD = 2000.0`), not driven by the
   `high_dollar_threshold` runtime config the docs imply. The config key is unused in the
   live path.
2. **`CG-BASIC-V1` AI/LLM findings are pre-pay only** — NULL confidence/amount, reviewed by a
   specialist into a correction letter; not part of the post-pay case disposition/at-risk
   flow. The post-pay "LLM rule needing human verification" is **DET-09 `needs_review`**.
3. **Notice-send endpoint is not role-gated** and can auto-advance a case to `notice_sent`,
   bypassing the $2,000 gate. The gate lives on the decision transition, not the letter.
4. **No auto-assignment by specialty** — the `specialty`/`supervisor_id` columns exist but
   assignment is entirely manual (self-assign or supervisor assign).
5. **Multi-role RBAC is not uniformly enforced** — live checks use the single `role` column.
