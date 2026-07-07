# Demo Script — Analyst Accepts a Suppressed Finding (Recoup Amount Follows the Analyst)

**Use case:** Multiple rules flag the same claim lines with different dollar theories. The
system defaults to the most defensible (highest-priority) amount, but the analyst — after
reviewing the evidence — validates the broader finding with one click, and the case's
At Risk total updates to use that finding's recovery amount. No double counting, full audit trail.

**Where:** https://payguard.penguinai.studio · **Login:** `rachel.burns` / `rachel.burns` (admin)
**Case:** `OPA-2026-00016` — Fee Schedule Mispricing, PPO, member Aaron Fitzgerald
**Duration:** ~3 minutes

> ⚠️ Every production deploy reseeds the demo data. If case 16 doesn't look like the
> numbers below, someone has already dispositioned it — redeploy (or pick another case
> showing the amber "Not counted in At Risk total" banner).

---

## The setup (say this first)

> "Three detection rules fired on this one claim. Two of them — fee schedule and NCCI —
> are narrow, contract-math rules. The third is an AI coding-review finding that says the
> documentation doesn't support the codes at all, putting **$255** at issue. All three
> point at the **same claim lines**, so we can't just add them up — that would demand the
> same dollars from the provider twice."

## Steps

### 1. Open the case
- Worklist → search `OPA-2026-00016` → open it.
- **Point at:** *Amount at Risk = $194.76*. "This is the system's default: for every claim
  line, count only the highest-priority rule's amount — the most defensible recovery."

### 2. Show the competing findings (Detector Results panel)
- **DET-04 Fee Schedule** — $104.76 (paid-minus-allowed deltas on three lines).
- **DET-06 NCCI** — $90.00 (mutually exclusive code pair; the lower-paid line).
- **DET-09 AI Coding Review** — $255.00, with the **amber banner**:
  *"Not counted in At Risk total — needs analyst review. This finding claimed $255.00 on
  lines already attributed to DET-04, DET-06 (higher dedup priority)."*
- **Say:** "The AI finding isn't lost — the system is explicit that its dollars overlap
  lines already counted, and that a human needs to make the call."

### 3. Review the evidence (optional, 20 seconds)
- Expand **Show Evidence** on DET-09: upcoding rationale on the E/M lines.
- **Say:** "The analyst reads the chart and agrees: the coding issue is real, and the right
  recovery is the full line payment, not just the fee-schedule delta."

### 4. Accept — one click, with an explicit dollar confirmation
- In the amber banner, click **"Accept — use this finding's amount."**
- An in-place confirmation appears: **"Confirm the $255.00 recoup for these lines?"** — it
  states that DET-09's amount will replace the lower-priority amounts on the shared lines
  and the total will recalculate.
- Click **Confirm $255.00**.

### 5. The payoff
- **Amount at Risk jumps $194.76 → $330.46.**
- Walk the math: DET-09 now owns its two lines ($165 + $90 = its full $255), **plus**
  DET-04 keeps its deltas on the two lines DET-09 never touched ($38.36 + $37.10).
  Every line counted exactly once.
- The banner moves: DET-04 now shows *its* overlap was superseded by the analyst-validated
  DET-09 — the display always tells you who owns which dollars.
- Open the **Audit Timeline**: the acceptance is logged with analyst, timestamp, and amounts.

### 6. (Optional) Same thing by voice — the Assistant
- Open the assistant panel on any similar case and type:
  *"Accept the DET-09 finding — the documentation supports full recovery of those lines."*
- It proposes the same action with a confirmation card; on Confirm, the same recompute runs.
  Works identically from the standalone (Claude Desktop) assistant via `perform_case_action`.

## Talking points if asked

- **"What if the analyst validates both rules?"** Then both are analyst-approved and the
  system falls back to detector priority for the shared lines — deliberate, deterministic.
- **"Can we get to exactly $255?"** Yes — *reject* DET-04 instead (wrong basis entirely):
  the lines reattribute automatically and the total becomes $255.00.
- **"Is Adjust as smart?"** Yes — adjusting a suppressed finding also promotes it to win its
  lines, then scales to the adjusted amount.
- **"Why not always take the bigger number automatically?"** Unreviewed AI theories inflating
  demand letters means disputes and overturns. Automation asserts what it can prove; the
  analyst's validation is what upgrades the claim — and it's one click, audited.
