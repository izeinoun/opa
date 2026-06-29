# Remediation & Enhancement Plan

> A followable, sequenced roadmap. Work top-to-bottom; phases are ordered by dependency. Each task: **Where** (file:line) · **Why** · **Verify** (how to confirm done) · size (S<2h / M<1d / L>1d). Check boxes as you go.
> Companion to the map in `docs/codebase-map/` — `risks-and-bugs.md` is the bug source; `reuse-map.md` is the enhancement source.
>
> **Golden rule:** every fix lands with (a) a reproducing check before, (b) the change, (c) a passing verify after. Don't batch unrelated fixes into one commit.

---

## Phase 0 — Verification gate ✅ DONE (2026-06-29)

Verified every P0/P1 against live code. **Result: 3 phantoms struck, saving the fix effort.** Status mirrored into `risks-and-bugs.md`.

- [x] 0.1 **Migrations-disabled** → ✅ REAL. `main.py:106-107` comments out `_run_migrations` ("hanging").
- [x] 0.2 **AI `detector_id`** → ✅ Code uses `CG-BASIC-V1` (`ai_service.py:41`); CLAUDE.md's `AI-CLAUDE-V1` is stale.
- [x] 0.3 **claimguard export** → ✅ REAL but **frontend-only**. Backend exists (`prepay_claims.py:1261/1300`, path `/api/prepay/claims/{id}/export/denial|approval`, needs `claimguard` app grant).
- [x] 0.4 **siu dashboard 404** → ❌ PHANTOM. Exists in `siu_dashboard.py` (`prefix=/api/siu/dashboard`, registered `main.py:176`).
- [x] 0.5 **ClearLink `search_members`** → ❌ PHANTOM. Enabled `agent_tools` row + MCP-listed + `toolExecutor.js:115` runs LLM fuzzy.
- [x] 0.6 **ClearLink MCP audit** → ✅ REAL. Object-vs-positional mismatch (`agentLogger.js:72` vs `mcpTools.js`).
- [x] 0.7 **DET-20** → ✅ REAL + exact cause: typo `BEHAVIORAL_HEALTH_CPts` (line 25) vs `self.BEHAVIORAL_HEALTH_CPTS` (line 82) → AttributeError on HMO claims.
- [x] 0.8 **provider_portal** → ❌ PHANTOM (wired at `main.py:141,195`); real issue = uncommitted in git.
- [x] 0.9 `risks-and-bugs.md` updated with verified-status column.

---

## Phase 1 — Documentation hygiene & context cleanup ✅ DONE (2026-06-29)

Archived/relocated everything stale; nothing deleted (reversible). Root now holds 4 docs.

- [x] 1.1 Inventoried all root docs with git-tracked status + reference checks.
- [x] 1.2 Created `docs/_archive/` (+ README index) and `docs/reference/`. Moved 9 completed/status docs + 4 scratch files (3× FOUR_LAYER, Vanessa txt, UPDATED.csv) to `_archive/`; 6 still-valid feature/plan docs to `reference/`. Used `git mv` for tracked files (history preserved).
- [x] 1.3 Chose **archive over delete** (many were untracked → deletion permanent). Decks/migrate-scripts left in place (not markdown context-polluters).
- [x] 1.4 **Revamped `CLAUDE.md`** — verified against code: ~23 detectors (not 6), `CG-BASIC-V1` (not AI-CLAUDE-V1), likelihood in `case_creation_service.py:360-366` (not analyze.py), **startup migrations disabled** warning, demo-gate→JWT reality, anthropic now present, suite-map pointer at top, ClaimGuard phases collapsed + linked, Known-bugs section added.
- [x] 1.5 Rewrote `claimguard/CLAUDE.md` → "backend merged into OPA; frontend-only thin client" + links to OPA map.

**Root after cleanup:** `CLAUDE.md`, `README.md`, `DATABASE.md`, `MCP.md` (+ `requirements.txt`). All other docs under `docs/reference/` or `docs/_archive/`.

---

## Phase 2 — P0 live-bug remediation · M (scoped to Phase-0-confirmed only)

Phantoms (old 2.3 siu-dashboard, 2.5 search_members) REMOVED — they work. Order: foundational schema first.

- [x] 2.1 **Re-enable / fix startup migrations** ✅ DONE — re-enabled in the lifespan via `asyncio.wait_for(asyncio.to_thread(_run_migrations), timeout=120)` + non-fatal try/except (so a stray lock can never hang startup forever). **Root cause: SQLite lock contention** from a 2nd process on `opa.db` (running dev server / `--reload` double-process) — the migration content itself builds from empty in ~0.2-0.7s. **Verified:** backend boots clean (`/health` ok); full suite 50/50 in 3s after killing a stray server (a concurrent server made tests hang — proving the mechanism). `alembic check` clean, DB at head.
- [x] 2.2 **Fix DET-20** ✅ DONE — was **3 layered bugs**, not 1: (a) typo `CPts`→`CPTS` (line 25, AttributeError); (b) every `DetectorResult` used non-existent fields (`detector_id`/`title`/`rationale`/`confidence`/`claim_line_id`) → TypeError once (a) was fixed — rewrote all 3 to the real dataclass fields (`detector_code`/`description`/`confidence_score`/`evidence` with `line_id` attribution); also simplified `run()` to the `(claim, db_session)` contract. Added `tests/test_det20_carveout.py` (5 tests). **Verified:** 5/5 pass, full suite 48/48. **✅ Follow-up RESOLVED (2026-06-29):** repointed DET-20 to `claim.raw_claim_json` (the real claim envelope) + made the DME check require a known non-approved vendor (no false positives); rewrote `seed_carveout_violation_claims.py` to the real `claims`/`claim_lines` schema. Verified end-to-end (seed → 3 findings) + 7 unit tests. See risks-and-bugs #23.
- [x] 2.3 **Fix claimguard export** ✅ DONE (frontend-only) — added `api.exportDenialZip`/`exportApprovalZip` (authenticated `client` blob GETs at `/api/prepay/claims/{id}/export/denial|approval`) in `claimguard/frontend/src/api/index.ts`; rewired both modals off raw `fetch`+wrong path; fixed the stale "not ported" comment. **Verified:** `tsc --noEmit` clean. (Not runtime-tested end-to-end — needs OPA backend + a claim + `claimguard` app grant on the demo user.)
- [ ] 2.4 **Fix ClearLink MCP audit** — change `mcpTools.js` `auditLog({...})` call to positional `auditLog(entityType, entityId, action, performedBy, details)` per `agentLogger.js:72`. **Verify:** an MCP `add_diagnosis` call inserts a row in `agent_tool_calls`/`audit_log`.
- [ ] 2.5 **Commit provider_portal** — it's wired (`main.py:141,195`) but untracked; `git add` `routes/provider_portal.py` + `services/provider_portal_service.py` (+ seed/migration if needed). **Verify:** end-to-end recoup-notice upload reaches mock portal :3002.
- [ ] 2.6 **(Investigate, not assume) siu dashboard** — endpoint exists; if the FE still errors, repro and check `require_app('siu')` 403 vs trailing-slash. **Verify:** siu DashboardPage renders OR root cause is a grant/shape issue logged for Phase 3.5.

---

## Phase 3 — P1 security & identity hardening · M

These are demo-acceptable but must be fixed before any real/non-synthetic data.

- [ ] 3.1 **Decide the live gate** — confirm JWT path vs demo gate (`gate.py` unregistered). Remove the dead one or re-register intentionally. **Verify:** one documented auth path.
- [ ] 3.2 **Real password hashing** — replace the placeholder check in `auth_service` with bcrypt/argon2. **Verify:** login works against hashed creds; no plaintext compare.
- [ ] 3.3 **ClearLink `add-diagnosis` auth** — actually apply the imported `requireApiKey`. **Verify:** unauthenticated call → 401; OPA's keyed call → 200.
- [ ] 3.4 **ClearLink CORS + JWT secret** — restrict `Access-Control-Allow-Origin` to known hosts; require a real `JWT_SECRET` (fail boot if `changeme_in_production`). **Verify:** cross-origin blocked; boot rejects default secret.
- [ ] 3.5 **Seed `apps[]` grants** — ensure seed gives demo users the app grants their `NoAccessGate` needs (siu/claimguard). **Verify:** demo users reach each app without blank-screen.
- [ ] 3.6 **Server-derived identity (design note)** — document the path from `X-User-Id` trust to real server-side identity (don't implement unless going to real data). **Done when:** P1 rows closed or consciously deferred with a note.

---

## Phase 4 — P2 cleanup (drift, dead code, config traps) · M

- [ ] 4.1 Delete dead `authService.ts` copies (siu, claimguard) after confirming no imports. **Verify:** build passes.
- [ ] 4.2 Fix/replace claimguard `scripts/prewarm.sh` (`:8002` → `:8001`, `/api/prepay/...` paths). **Verify:** script warms a real OPA endpoint.
- [ ] 4.3 Consolidate ClearLink to **one** Claude client + one model config (kill the sonnet-4-6/opus-4-8 split). **Verify:** all LLM calls share one config point.
- [ ] 4.4 Single URL source per frontend — make `appUrls.ts` the only source; remove AppSwitcher's divergent `VITE_*` reads (or vice-versa, but pick one). **Verify:** changing one place changes all links.
- [ ] 4.5 POST or drop the intake/claimguard step-1 metadata form (currently silently discarded). **Verify:** entered data either reaches backend or the fields are removed.
- [ ] 4.6 Fix intake-portal port doc (5180→5181) and `headless` flag in mock-portal `playwright-upload.js:52` for CI. **Verify:** docs match; script runnable headless.
- [ ] 4.7 De-dupe MCP identity-resolution between `mcp_mount.py` and `mcp_server.py`. **Verify:** one shared helper.
- [ ] 4.8 Make the detector orchestrator surface failures (keep swallowing for resilience, but log at ERROR + increment a counter / health field). **Verify:** a forced detector exception shows up loudly.

---

## Phase 5 — Enhancements & reuse extractions · L (prioritized)

From `reuse-map.md`, highest blast-radius first. Each: extract canonical → migrate consumers → delete copies.

- [ ] 5.1 **Shared frontend auth/identity package** — `DemoGate` + `ActorPicker` + `NoAccessGate` + `appUrls` into one shared module consumed by all 5 SPAs + OPA client. Standardize the actor localStorage key. **Why:** biggest drift surface; centralizes the `X-User-Id` boundary. **Verify:** all apps log in/switch actor via the shared code; per-app copies deleted.
- [ ] 5.2 **`useAssistantChat` hook** — extract SSE parse + `ask_user`/`tool_result` rendering + `awaiting_confirmation` write-gate + `sanitizeAssistantOutput` from the 4 `AssistantPanel`/`AssistantChat` copies. **Verify:** OPA client + standalone assistant + siu + claimguard all use it; behavior unchanged.
- [ ] 5.3 **Consolidate member fuzzy search** — one canonical service (per [[member-fuzzy-search-pattern]]); have OPA and ClearLink share the prompt/contract instead of two drifting variants. **Verify:** identical match behavior from both entry points; no SQL-LIKE name search remains.
- [ ] 5.4 **Complete ClaimGuard merger** (Phase 2/3 from CLAUDE.md) — port remaining endpoints (provider messages, evidence search, ZIP export), comments→`case_notes`, `/config`→`/api/runtime-config`, UUID switch, then **delete** `claimguard/backend/`. Full list: `projects/claimguard.md` MERGER_TODO. **Verify:** claimguard SPA fully runs on OPA; old backend gone.
- [ ] 5.5 **DET-18 medical-necessity accuracy** — Option A (expand `cpt_dx_coverage` catalogue in `seed/seed_codes.py`) then Option B (LLM fallback for uncatalogued CPTs, gated by `ai_suggestions_enabled`). **Verify:** more covered CPT families; LLM fallback returns an AI finding for an uncatalogued CPT.
- [ ] 5.6 **Unify finding taxonomy** (severity `low/med/high` vs `critical/warning/ok`; detector_id vocab) — decide one mapping. **Verify:** a documented severity mapping; both pipelines write consistent values.

---

## Phase 6 — Guardrails (lock in the gains) · M

- [ ] 6.1 **CI drift guard** — `alembic upgrade head && alembic check` must pass; fail CI on non-empty diff. **Verify:** a model change without migration fails CI.
- [ ] 6.2 **Smoke tests per cross-app edge** — one test each for: each SPA→OPA auth, OPA→ClearLink MCP, OPA→mock-portal upload, assistant stream. **Verify:** `make test` green; broken edge fails fast.
- [ ] 6.3 **Audit-completeness check** — assert every MCP/tool call and case mutation writes an audit row (catches regressions like the ClearLink audit bug). **Verify:** a tool call without an audit row fails the test.
- [ ] 6.4 **Keep the map current** — add a checklist item to PRs: "updated `docs/codebase-map/` if structure changed." **Done when:** guardrails in CI; map-update is part of the PR template.

---

## Suggested cadence

1. **Day 1:** Phase 0 (verify) → Phase 1 (docs/CLAUDE.md) — clean foundation.
2. **Days 2-3:** Phase 2 (P0 bugs) — restore broken features.
3. **Day 4:** Phase 3 (security) + Phase 4 (cleanup).
4. **Week 2+:** Phase 5 (enhancements, one extraction at a time) → Phase 6 (guardrails).

**Dependencies:** 0 → everything. 1 before 2 (clean context). 2.1 (migrations) before any schema-touching task. 5.1 before 5.2 (shared package hosts the hook). 5.4 (merger) before deleting claimguard backend.

**Per-task commit discipline:** branch per phase, one logical fix per commit, verify step in the commit body, update `risks-and-bugs.md` status as you close items.
