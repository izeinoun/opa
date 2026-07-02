# Feature Guide — Analyst & Supervisor

**Audience:** claim analysts/specialists and their supervisors.
**Scope:** the two review pipelines on the platform — **PayGuard** (post‑pay recovery) and **ClaimGuard** (pre‑pay review) — plus the shared AI assistant and dashboards.

---

## 1. What the platform does

The platform is a healthcare **payment‑integrity** workbench. It runs a library of
rule‑based detectors (plus AI/LLM analysis) against claims, turns the results into
**cases** with a priority and a dollar amount at risk, and walks you through a
review → decision → provider‑notice → recovery workflow with a full audit trail.

- **PayGuard (post‑pay):** claims already paid. Goal — find overpayments and recover them.
- **ClaimGuard (pre‑pay):** claims not yet paid. Goal — approve, deny, or correct before payment.

Both pipelines share **one detector engine** and the same evidence sources
(claim data → attached documents → ClearLink member records).

---

## 2. Core concepts

| Concept | Meaning |
|---|---|
| **Case / Claim** | A unit of work. PayGuard groups findings into a *case*; ClaimGuard reviews a *claim* directly. |
| **Finding** | One rule that fired (e.g. duplicate, NCCI edit, medical necessity), with a rationale and evidence. |
| **Rule confidence** | The detector's fixed confidence in a finding (a per‑rule weight, not a per‑claim probability). |
| **Priority score** | 0–100 blend of dollars at risk, likelihood, and urgency. Bands: **HIGH ≥75 / MED 50–74 / LOW <50**. |
| **Amount at risk** | Pipeline‑aware dollars each finding puts at risk (deduplicated per claim line). |
| **Disposition / Decision** | The outcome you assign: recoup / not‑for‑recoup (PayGuard); approve / deny / correct (ClaimGuard). |

---

## 3. Analyst features — PayGuard (post‑pay)

### 3.1 Worklist & prioritization
- **Worklist** ranks your open cases by priority so the highest‑value, highest‑likelihood work rises to the top.
- Personal **Analyst Dashboard** shows your queue, aging, and recovery metrics; the main **Dashboard** gives team/portfolio views.

### 3.2 Case review
- **Case Detail** shows the claim, member, **rendering provider and their Provider Org**, the list of **findings** with rationale, the **amount at risk**, and the computed **likelihood/posterior**.
- Findings are attributable per claim line, so you can see exactly what drives the dollars.

### 3.3 Evidence & documents
- **Evidence panel:** upload medical records (`kind=medical_record`); the system extracts text and runs an **AI evidence‑validation** pass that cross‑checks the chart against the claim.
- Detectors also consult **attached documents** and **ClearLink** member records (diagnoses, prior authorizations, clinical notes) when the claim alone is insufficient.

### 3.4 Decision workflow
- Move a case through: **start review → decide → (supervisor approval if high‑dollar) → notice → recovery → close.**
- Decisions above the configured **high‑dollar threshold** are automatically held for supervisor approval.

### 3.5 Provider communication
- **Send to Provider** (split action on the case):
  - **Secure Email – Notice:** emails the provider an NPI‑verified secure link to download the recoupment letter (the provider authenticates with their billing NPI before the PDF is served).
  - **Send Inquiry:** compose a custom secure message.
- **Upload to Provider Portal:** pushes the recoupment notice to the provider's portal via browser automation. Available at any time; warns (without blocking) if a notice was already delivered.
- Both actions confirm success/failure inline, and remain available through the active delivery window.

### 3.6 Letters & recovery
- Generate the **recoupment letter** from the case; it is stored and delivered by email or portal.
- **Delivery Queue** lists cases awaiting a notice; **Output Files** collects generated documents.
- Track recovery through to **Closed Cases** with recovery/write‑off outcomes.

### 3.7 Remittance (835) analysis & intake
- **Analyze 835** ingests remittance advice; **File Intake** / **Unmatched Documents** handle inbound files and reconcile documents to claims.

---

## 4. Analyst features — ClaimGuard (pre‑pay)

### 4.1 Claims queue & detail
- **Claims Queue** lists pre‑pay claims with status, CPTs, billed amount, and priority.
- **Claim Detail** tabs: **Claim Details**, **AI Findings**, **Evidence Check**, **Documents**, **Comments**, **Audit Trail**.

### 4.2 AI Findings
- Header shows **"N fired / M run"** — how many rules triggered vs. how many were evaluated — plus critical/warning counts when present.
- Each finding shows a **generic rule description** and a **claim‑specific plain‑English explanation** (AI‑generated), its **Rule confidence**, and the mapped **CMS denial code (CARC)**.
- **Accept / Reject** each finding to record your review.

### 4.3 Recommendation & decision
- A **Recommendation** card gives a suggested action (approve / reject / review) with an overall evidence score.
- **Denial letter:** one click generates a standard **CMS‑coded denial‑letter PDF**, attached to the claim's Documents and shown in a PDF viewer. It regenerates on re‑analysis and on deny.

### 4.4 Documents & evidence
- **Documents** tab: per‑document **View / Download / Delete**; View opens the PDF inline.
- **Evidence Check** cross‑references attached chart documents and ClearLink records against the claim.

---

## 5. The AI Assistant

Available in both apps as a chat panel. Ask about a specific case, claim, provider,
member, or your own productivity metrics; draft provider inquiries; and get
next‑step guidance. It reads live case/claim data and confirms any outward action
(e.g. sending a message) before it happens.

---

## 6. Supervisor features

Supervisors have everything above, plus oversight tools:

- **Approvals:** review and approve/deny analyst decisions that exceed the high‑dollar threshold before they execute.
- **Team Performance / Team Monitor:** throughput, recovery totals, aging, and per‑analyst productivity.
- **Assignments:** assign or reassign cases across the team; **Team view** vs. **My view** toggles.
- **Escalations → SIU:** hand a case to the Special Investigations Unit when fraud/abuse is suspected; escalated cases move out of the standard queue.
- Full visibility into **Worklist**, **Closed Cases**, and **Delivery Queue** across the team.

---

## 7. Roles at a glance

| Capability | Analyst | Supervisor |
|---|:---:|:---:|
| Review cases/claims, record findings decisions | ✓ | ✓ |
| Generate letters, send to provider / portal | ✓ | ✓ |
| Upload evidence, run AI analysis, use assistant | ✓ | ✓ |
| Approve high‑dollar decisions | — | ✓ |
| Team performance, assignments, escalate to SIU | — | ✓ |

*Access is governed by role + app permissions; the exact tabs you see depend on your assigned apps (PayGuard / ClaimGuard / SIU).*
