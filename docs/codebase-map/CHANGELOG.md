# Cross-cutting Change Log

History of suite-wide changes since the context map was created (2026-06-29). The master project (OPA) records cross-app changes here so the holistic view stays current. Newest first. Each entry: what changed, who/where, verification status.

---

## 2026-06-29 — Cross-app identifier normalization (member + claim keys)

**By:** a separate session running under the `claimguard` project. **Documented in:** `cross-cutting/data-models.md` §Identifier normalization.

**Intent:** unify the member business key and the claim human-readable number across PayGuard (OPA), ClaimGuard, and ClearLink.
- ClearLink `members.member_id` → **`member_number`** (TEXT business key); `claims.claim_number` → **`icn`**; CEE JSON `metadata.claim_number` → `metadata.icn`.
- OPA already used `member_number` / `icn`; added `member_number` to `PrepayClaimOut`/`Detail` as the cross-system join key.

**Master verification (this project):**
- ✅ DB schema renamed correctly (ClearLink `members.member_number`, `claims.icn`).
- ✅ OPA side complete + correct (`prepay_schemas.py:95`, `prepay_claims.py:312,620`).
- ✅ Join verified: OPA `members.member_number` == ClearLink `members.member_number` (Stacy Truman `123456` on both).
- ❌→✅ **ClearLink propagation was INCOMPLETE — now FIXED (2026-06-29).** Found 5 old-name refs (3 on the live MCP path): 2 DB-resident SQL connectors (`get_claims_window`, `get_member_demographics`) + `toolExecutor.js:86` (systemic member resolution) + `memberUtils.js:3` + `seed.js:93`. The audit's "old names gone from server code" claim was false (it couldn't see the DB-resident connector SQL). **Fix applied by master (this project):** column names swapped to `member_number`/`icn`; ClearLink restarted; bridge re-verified via `executeMcpTool` for Stacy (123456) — demographics return `mrn:123456`, diagnoses + claims (`icn`) return, unknown member errors cleanly.
- **Net:** identifier normalization is now complete + consistent across all 3 systems. Cross-system join (`OPA.members.member_number = ClearLink.members.member_number`) verified working through the live MCP bridge.

---

## 2026-06-30 — API security + assistant UX (auth gate, login wall, context mgmt, spinner)

- **REQUIRE_AUTH gate (OPA backend):** opt-in middleware (env `REQUIRE_AUTH=1`, off by default) that requires a logged-in/resolved user on every `/api/*` route except `/api/auth/*` and `/health`. Registered before CORS so 401s keep CORS headers; covers endpoints that don't use `get_current_user` (e.g. `/api/users`). Shared `resolve_user_id()`. Verified with the flag on; suite 50/50 with it off. **Activation note:** enabling it requires every served frontend to authenticate first — PayGuard + ClaimGuard do (UI gated behind login); siu/iam/intake-portal bootstrap unauthenticated and need a login wall before activation.
- **ClaimGuard login wall:** replaced the fail-open `DemoGate` (checked the removed `/api/auth/status`) with a JWT username/password `AuthGate` that fails closed. Cross-origin: stores the login's `access_token` as a Bearer token (not the SameSite=Lax cookie). Verified against the live backend.
- **Assistant context management (shared `agent.py`):** `_manage_context()` bounds the history sent to Claude (stub old tool_result payloads, cap at clean turn boundaries) without breaking tool_use/tool_result pairing.
- **Assistant "thinking" spinner:** Send button shows a spinner while working, across all four assistant UIs.
- **Auth consolidation (retired the vestigial demo gate):** audited the API auth and found the old `DEMO_PASSWORD`/HMAC Bearer gate was dead (middleware unregistered, token validated nowhere) — confusing tech-debt alongside the live mechanisms. Deleted `middleware/gate.py`, removed `DEMO_PASSWORD` + the dead `make_token()` self-call headers (`mcp_mount`/`agent`), switched the MCP mount to in-process DB identity resolution (so it works under `REQUIRE_AUTH`), and fixed the standalone `mcp_server.py`/`mcp_remote.py` to JWT username/password login (`access_token`). Fixed stale comments in config/main/railway.toml. **Result:** API auth = JWT (users) or API key (services) on `Authorization: Bearer` + `X-User-Id`, enforced by `REQUIRE_AUTH`. Suite 50/50.

These are committed + pushed across opa, claimguard, assistant, siu.

---

## 2026-06-29 — DET-18 ClearLink cross-system medical-necessity check fixed

DET-18 (medical necessity) is designed to satisfy a CPT's required dx from THREE sources: the claim's own dx, **documents attached to the PayGuard case** (regex-extracts ICD-10 from `Document.extracted_text`), and **ClearLink** (the member's clinical diagnoses). The document path worked; the **ClearLink path was silently broken** — the helper called a non-existent tool (`get_member_medical_records`) and passed OPA's UUID `member_id` instead of the `member_number` ClearLink resolves on, so it always returned an empty set.

**Fixed:** `clearlink_detector_helper.search_clearlink_for_diagnoses` now calls `list_diagnoses`; DET-18 resolves `member_id`→`member_number` before querying. **Verified end-to-end** on Stacy's CPT 27447 claim: DET-18 fires at baseline, then turns OFF after `M17.11` osteoarthritis is added to ClearLink — the two-step demo works.

**Extended to all ClearLink-backed detectors (enterprise: use all available data).** The same bug class was fixed across DET-04/06/09: `search_clearlink_for_prior_auth` → `list_prior_authorizations`; `search_clearlink_for_clinical_notes` → aggregates real ClearLink narrative (`list_diagnoses` + `get_provider_messages`, since ClearLink has no clinical-notes tool). Member resolution was centralized in `BaseDetector.resolve_member_number` (DET-18's private copy removed). Each detector already checked attached case documents first; this restores the ClearLink fallback so adjudication uses **both** the payer's own document store AND the connected clinical system. Verified (prior-auth True/False by CPT; clinical-notes keyword match; suite 50/50). OPA backend restarted.

---

## 2026-06-29 — Session fixes (OPA + ClaimGuard) prior to the rename

Recorded for history; all verified this session.
- **Migrations re-enabled** (`opa/server/app/main.py`) with timeout + non-fatal guard; root cause was SQLite lock contention, not the migrations. (risks #1)
- **DET-20 carve-out detector** fixed (typo + wrong `DetectorResult` fields + data source repointed `case_json`→`raw_claim_json`) and its seed rewritten to the live schema. 7 unit tests, suite 50/50. (risks #6, #23)
- **ClaimGuard denial/approval export** fixed (authenticated `api.exportDenialZip`/`exportApprovalZip`; was wrong path + no auth). (risks #2)
- **PayGuard assistant** (`AssistantPanel.tsx`) fixed — 6 undefined refs in the dead modal-mode branch broke `tsc`/build; mapped to the real drawer-mode handlers + imported `Check` + wrapped the drawer in an `ErrorBoundary`. Browser-verified: assistant streams live with tool calls.
- **Docs hygiene:** root docs archived/relocated; `CLAUDE.md` revamped to verified facts; sibling `claimguard/CLAUDE.md` rewritten to "backend merged into OPA".

---

## 2026-06-29 — Context map created

Initial 8-project map: `INDEX.md`, `projects/*.md`, `cross-cutting/*.md`, `ACTION-PLAN.md`.
