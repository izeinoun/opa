# PayGuard — Customer Demo Script

*Single-page click-by-click. Keep this open on a second screen. Bold = what you **say**; `code` = what you **click/type**.*

**The story arc:** a reviewer opens their queue → the system has already ranked cases by *expected recoverable value* → they open the top case and see an **AI clinical rule** catch a coding error with a cited source → they ask *"why is this provider on the radar?"* and get a transparent SHAP explanation → then we lift up to the **model + capacity plan** that drives it all.

---

## 0 · Pre-flight (2 minutes before the call)

- [ ] Both servers up: backend `:8001`, frontend **`:5174`**.
- [ ] **Use `http://localhost:5174`** — NOT `localhost:8001` and NOT the penguinai.studio site. (Those hit a different backend and the demo data / login won't behave.)
- [ ] Log in: go to `http://localhost:5174` → **type** `rachel.burns` / `rachel.burns` by hand. **Dismiss any browser autofill** — a saved password will fail.
- [ ] Pre-warm the LLM case: open `http://localhost:5174/cases/13` once so it's cached. (Already re-run; DET-09 fires.)
- [ ] Have these tabs/URLs ready: **`/overview`** (opening slide), `/` (worklist), `/cases/13`, `/provider-risk`, and Admin → **ML Model**.

**Do NOT drill into `OPA-CAP-*` cases** during the review story — they're synthetic background volume for the capacity plan; their detail pages aren't curated. Use the `OPA-2026-*` cases.

---

## 0 · Set the stage — the platform overview

**Click:** open **`/overview`** (left nav → **Overview**). *This is your opening slide — talk over it before touching any real data.*

**Say:**
- **The suite:** *"We're a payment-integrity suite — six apps, one backend. Claims come in through the **Intake Portal**; **ClaimGuard** catches overpayments **before** payment; **PayGuard** — where we are today — recovers them **after**; **SIU** handles fraud investigations; **IAM** governs access; and an **AI Assistant** runs across all of it."*
- **The workflow (point along the row):** *"A case moves left to right: a claim arrives, our rules and AI detect issues, it's prioritized by expected value, an analyst reviews it, decides, and we recover the money."*
- **The engine (point along the pipeline row):** *"Two calibrated ML models drive it — one scores the **provider's reputation**, the second scores each **claim** using that reputation plus the claim's own features. The models decide **where to look**; the rules decide **what's recoverable**. That's the whole idea — and everything you'll see next is that flow in action."*

*Then dive into the live app ↓*

---

## 1 · The reviewer's worklist — priority is *expected value*, not dollars

**Click:** land on the **Worklist / Intake List**.

**Say:**
- *"This is what an auditor sees each morning — every open case, already prioritized for them."*
- *"The key idea: priority isn't the dollar amount. It's **expected recoverable value** — how confident we are the overpayment is real, times the dollars at stake. `evidence × amount`."*
- *"So a reviewer's scarce time always goes where it will actually recover money — not to the biggest sticker price."*

**Point at the top of the list:** `OPA-2026-00015` — **$7,530**, priority **100 (HIGH)**. *"Big dollars **and** strong evidence — top of the queue."*

**Then point at `OPA-2026-00021` — the money shot:** *"Here's the one that makes the point. It's our **second-biggest case by dollars — $6,480** — but look where it ranks: priority **~25**, *below* the $1,770 and $1,386 cases above it. Why? It has a **single weak finding — 18% confidence**. Big sticker price, but we're not confident it'll stick, so its expected value is only ~$1,300. The system won't spend an auditor's morning on it until the stronger cases are cleared."* (Read across its row: **Prior 5.3% → Posterior 20.5%** — the rules barely moved the needle — **× At Risk $6,480 = EV $1,326 → Priority 25**. The posterior column is the tell: contrast it with 00013's 99.7%.)

**Then scroll down:** *"And the mirror image: small-dollar cases sink even with rock-solid findings — a $50 finding just isn't worth an auditor's hour. Dollars alone don't rank a case; **evidence × dollars** does. That's the whole point — the model protects reviewer time."*

**For a technical / AI audience, read the `Prior → Posterior → At Risk → EV` columns across the row:** *"We don't hide the work behind one number — you can watch the belief update across the row."*
- ***Prior*** *— the Stage-2 claim model's calibrated probability that *this specific claim* is an overpayment, **before the rules run**. Shown raw (not normalized), so it's honestly small: a true probability on a rare event. (The Stage-1 provider-reputation score feeds that model as one input — decomposed on the provider's risk profile.)*
- ***Posterior*** *— the probability **after the detector rules corroborate** (a noisy-OR over the fired findings). This is the leap: a 4% prior becomes a **99.7%** posterior once strong coding-error rules fire.*
- ***EV = Posterior × At Risk*** *— the expected recoverable value. You can check the arithmetic right on screen: 99.7% × $1,770 = $1,765.*

*"So the pipeline is legible end to end: model prior → rules update it to a posterior → posterior weights the dollars into EV → EV drives priority. The model did the case-selection work; the row shows exactly how each case earned its rank."* (Both `Prior` and `Posterior` have ⓘ tooltips.)

---

## 2 · Inside a case — the AI clinical rule fires

**Click:** open **`OPA-2026-00013`** (the migraine / knee-replacement case).

**Say (set it up):**
- *"Here's a claim: a patient with a **migraine** diagnosis, billed for a **total knee replacement** — $1,770."*

**Click:** the **`↺ Re-run`** (or "Re-run detectors") button. *(Watch the rules re-run live; the review-outcome message appears when it finishes.)*

**Say (while it runs):**
- *"I'm re-running our rules. Most are deterministic edits — but two are **LLM-backed**: they read the claim and reason about it clinically."*

**When it finishes, point at the DET-09 "Coding Errors" finding:**
- Read the rationale: *"Diagnosis G43.909 (migraine) does not support procedure 27447 (total knee arthroplasty). Migraine has no clinical relationship to knee replacement. Extreme DX-procedure mismatch."*
- *"And critically — it **cites the source**: CMS LCD L34041. The reviewer gets a defensible, sourced explanation, not a black-box score."*
- *"This is the difference: our AI rules catch the probabilistic, clinical-reasoning cases the hard-coded edits can't — and hand the auditor evidence they can act on."*

**Optional:** click **`Take ownership`** → **`Start review`** to show the reviewer workflow (case assigns to Rachel, moves to In Review).

---

## 3 · "Why is this provider on the radar?" — transparent SHAP

**Click:** left nav → **Provider Risk** (`/provider-risk`). Expand **Dr. Grant Abrams** (HIGH, 0.96).

**Say:**
- *"Every provider gets a reputation score from an ML model on their billing behavior. And it's fully explainable — no black box."*
- Walk the decomposition top to bottom:
  - **Base value 0.500** — *"the average provider."*
  - **prior overpayment rate 50% vs 27% typical → +0.221** — *"the biggest driver."*
  - **specialty peer deviation, units/line → +0.10, +0.04.**
  - **= Model output 0.930.** *"It adds up exactly: base + every contribution = the score. The displayed 0.96 is just the calibrated version."*
- *"So when we tell a payer 'watch this provider,' we can show precisely **why** — which is what survives an audit and a provider dispute."*

---

## 4 · The engine behind it — model + capacity plan

**Click:** Admin → **ML Model** page. Scroll top to bottom — it reads as the pipeline.

**Stage 1 — Provider Reputation:**
- *"Scores providers. We judge it on **ranking (AUC ~0.96)** and **calibration (Brier)** — because its output is a probability we feed forward, not a yes/no flag."*

**Stage 2 — Claim Predictor:**
- *"Scores each **claim** from its own payment features **plus** the provider's reputation score. Also calibrated — so its probability is a true likelihood."*

**Audit Plan (the money slide):**
- **Say:** *"Now the operational question every payer asks: **my team can review N cases a month — how much money do we actually capture?**"*
- Show the two knobs: **set capacity → get % of EV captured**, or **set a capture target → get the capacity needed.**
- Point at the **cumulative-EV curve**: *"Here's the punchline — with just **50 cases we capture ~97% of the recoverable value**. The curve is steep then flat: the first cases carry the dollars. So you don't need to review everything — you need to review the **right** cases. That's what this system delivers."*

---

## Closing message

*"So end to end: we rank by expected value so your team works the highest-yield cases first; our AI rules catch clinical errors the edits miss and cite the source; every score is explainable for audits and disputes; and the capacity plan tells you exactly how much you'll recover for the review effort you can afford. That's PayGuard."*

---

## If something goes wrong

| Symptom | Fix |
|---|---|
| Login fails | Type `rachel.burns` / `rachel.burns` by hand; dismiss browser autofill. |
| No findings / "Take ownership" does nothing / stale data | You're on the wrong URL. Must be **`http://localhost:5174`**, not `:8001` or penguinai.studio. |
| Assistant/LLM error | API key issue — the working key is in `server/.env`; restart the backend. |
| A case detail looks inconsistent | You opened an `OPA-CAP-*` synthetic case. Use the `OPA-2026-*` curated cases instead. |
| Re-run seems stuck | It makes live LLM calls (~20–30s). Give it a moment; the outcome message appears when done. |
