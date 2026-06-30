# Risks & Live Bugs — consolidated troubleshooting hotlist

> Ranked by blast radius. Each entry: symptom → location → fix direction. Check here FIRST when something is broken.
> **STATUS column added after Phase 0 verification (2026-06-29).** ✅=confirmed real · ❌=phantom (snapshot wrong) · ⚠️=real but rescoped.

## P0 — live functional bugs (broken now)

| # | Status | Symptom | Location | Fix direction |
|---|--------|---------|----------|---------------|
| 1 | ✅ FIXED (2026-06-29) | **OPA schema not built in-process** — migrations were disabled at startup | `main.py` lifespan | DONE: re-enabled `_run_migrations` via `asyncio.wait_for(asyncio.to_thread(...), timeout=120)` + non-fatal try/except. **Root cause: SQLite lock contention** — a 2nd process on `opa.db` (a running dev server, or `--reload`'s double-process) blocks the migration's write lock. Verified: server boots clean; full suite 50/50 in 3s once a stray server is killed (a concurrent server made tests hang — proving the mechanism). Migration content is fine (full build from empty = ~0.2-0.7s). |
| 2 | ✅ FIXED (2026-06-29) | **claimguard denial/approval export broken** | FE modals used wrong path + raw `fetch` (no auth). Backend was fine (`prepay_claims.py:1261/1300`). | DONE: added `api.exportDenialZip`/`exportApprovalZip` (authenticated blob GETs) + rewired both modals. `tsc` clean; not runtime-tested e2e. |
| 3 | ❌ PHANTOM | ~~siu DashboardPage always 404s~~ | Endpoint EXISTS: `routes/siu_dashboard.py` `prefix="/api/siu/dashboard"` + `@router.get("")` (line 366), registered `main.py:176`. Snapshot only grepped `siu.py`. | If FE still fails: check `require_app('siu')` → 403 (missing app grant) or trailing-slash mismatch — NOT a missing endpoint. |
| 4 | ❌ PHANTOM | ~~ClearLink `search_members` uncallable~~ | Enabled row EXISTS (`agent_tools`: `search_members\|sql\|1`); MCP-listed via `toolProvider.js` (`WHERE enabled=1`, special-cased line 68); `toolExecutor.js:115` intercepts name → runs LLM `fuzzySearchMembers`. | None — works. (Row `kind=sql` but executor overrides to LLM fuzzy.) |
| 5 | ✅ REAL | **ClearLink MCP audit rows silently dropped** | `clearlink/server/routes/mcpTools.js` calls `auditLog({entity_type,...})` (object) but def is positional `auditLog(entityType, entityId, action, performedBy, details)` (`agents/agentLogger.js:72`) | Fix call to positional args → restores MCP audit trail. |
| 6 | ✅ FIXED (2026-06-29) | **DET-20 dead — 3 layered bugs** | (a) typo `CPts` vs `CPTS` → AttributeError; (b) all `DetectorResult`s used non-existent fields → TypeError. | DONE: typo fixed + all results rewritten to real dataclass fields w/ `line_id` evidence; `run()` simplified. 5 unit tests (`tests/test_det20_carveout.py`), suite 48/48. See P2 #23 for the remaining `case_json` mapping gap. |

**Phase 0 net:** 3 confirmed P0 (1, 5, 6) + 1 frontend-only (2); 2 phantoms struck (3, 4). Also struck: provider_portal "unwired" (#20) — it IS registered (`main.py:141,195`), only uncommitted in git.

## P1 — security / identity exposure

| # | Risk | Location | Note |
|---|------|----------|------|
| 7 | ⚠️ MITIGATED (2026-06-30) — **the API was open** (anonymous → `system` fallback). Added an opt-in `REQUIRE_AUTH` gate: `/api/*` rejects anonymous callers (401), existence-checks the user (bogus `X-User-Id` → 401). Still: `X-User-Id` of a *real* user is accepted (spoofable if an id is known) — true per-user security needs server-derived identity/SSO. Enable via `REQUIRE_AUTH=1` once siu/iam/intake have login walls. | `auth.py` `resolve_user_id`, `main.py` `_require_auth_gate` |
| 8 | **OPA demo gate present but NOT registered** | `middleware/gate.py` vs `main.py:125` JWT path | Confirm which gate is live; password check in `auth_service` is a placeholder (no bcrypt). |
| 9 | **ClearLink `add-diagnosis` route has no auth** | `clearlink/server/routes/` add-diagnosis (imports `requireApiKey`, doesn't use it) | OPA calls it server-side; still open if exposed. |
| 10 | **ClearLink wide-open CORS `*` + default `JWT_SECRET='changeme_in_production'`** | clearlink server config | Lock CORS, set real secret. |
| 11 | **NoAccessGate blank-screens users missing `apps[]` grant** | siu/claimguard frontends + OPA seed | Ensure seed populates `apps` for each user. |

## P2 — drift / dead code / config traps

| # | Issue | Location |
|---|-------|----------|
| 12 | Orchestrator swallows ALL detector exceptions → silent missing findings | `detectors/orchestrator.py` |
| 13 | Dead `authService.ts` (cookie+BroadcastChannel) conflicts with live Bearer gate | siu, claimguard (+ docs claim it in iam where absent) |
| 14 | claimguard `scripts/prewarm.sh` targets retired `:8002` | claimguard/scripts |
| 15 | Two ClearLink Claude clients, conflicting model defaults (sonnet-4-6 vs opus-4-8) | `toolExecutor.js`/`intake.js` vs `claudeClient.js` |
| 16 | API base URL committed in `appUrls.ts` (not env) but AppSwitcher reads `VITE_*` — two sources diverge | all frontends |
| 17 | intake-portal/claimguard step-1 metadata form silently discarded (never POSTed) | `intake-portal/src/App.tsx`, claimguard intake |
| 18 | intake-portal port mismatch (README 5180 vs vite 5181) | intake-portal |
| 19 | mock-provider-portal `playwright-upload.js:52` `headless:false` → breaks in CI/Railway | mock-provider-portal |
| 20 | ~~provider_portal not wired~~ → ❌ PHANTOM: registered at `main.py:141,195`. Real issue: just **uncommitted in git** (`??`) — commit it. | OPA |
| 21 | MCP identity-resolution duplicated `mcp_mount.py` vs `mcp_server.py` | OPA |
| 22 | Unported ClaimGuard endpoints (provider messages, evidence search) surfaced in UI w/o fallback — ZIP export now wired (2026-06-29) | claimguard frontend ↔ OPA |
| 23 | ✅ FIXED (2026-06-29) | **DET-20 carve-out feature mis-plumbed** — read metadata off `claim.case_json` (a field on `OpaCase`, not `Claim`) so it never fired BH paths + false-positived DME; and the untracked seed inserted bogus columns (`case_json`, `service_date`, `patient_name`…) while omitting 9 required NOT NULL columns. | DONE: detector now reads `claim.raw_claim_json` (the claim envelope) + DME only flags a known non-approved vendor (no more false positives). Seed rewritten to the real `claims`/`claim_lines` schema. Verified end-to-end: seed inserts 3 claims → DET-20 emits 3 correct findings; 7 unit tests + suite 50/50. |
| — | ℹ️ **Migrations verified (2026-06-29):** live `opa.db` at head `9fe5c480c840`; `alembic current`==`alembic heads`; `alembic check` clean (no model/migration drift). The startup-disable (#1) is a runtime-hang issue only, not a schema issue — re-enabling on the current DB is a no-op upgrade. | — |
| 25 | ✅ FIXED (2026-06-29) | **DET-18 ClearLink cross-system check was silently broken.** DET-18 is designed to satisfy medical-necessity from the claim dx + attached case documents + ClearLink. The ClearLink half called non-existent tools (`get_member_medical_records`) and passed OPA's UUID `member_id` instead of `member_number` → always returned empty. FIXED: helper now calls `list_diagnoses`; DET-18 resolves `member_id`→`member_number` (`_resolve_member_number`) before querying. Verified two-step on Stacy: fires on 27447, then turns OFF after M17.11 added to ClearLink. **✅ Related ALSO FIXED (2026-06-29):** `search_clearlink_for_prior_auth` → now calls `list_prior_authorizations`; `search_clearlink_for_clinical_notes` → now aggregates real ClearLink narrative (`list_diagnoses` + `get_provider_messages`) since ClearLink has no notes tool. DET-04/06/09 now resolve `member_number` before the ClearLink fallback (via shared `BaseDetector.resolve_member_number`; DET-18's private copy removed for DRY). Verified: prior-auth True for authorized CPT 93000 / False for 27447; clinical-notes keyword match True/False correctly; suite 50/50. | `det_18`, `det_04`, `det_06`, `det_09`, `base_detector.py`, `clearlink_detector_helper.py` |
| 24 | ✅ FIXED (2026-06-29) | **Identifier rename incomplete → ClearLink MCP bridge broken.** Cross-app rename left 5 old refs in ClearLink (2 `agent_tools` SQL connectors + `toolExecutor.js:86` + `memberUtils.js:3` + `seed.js:93`). FIXED: column names swapped to `member_number`/`icn`, ClearLink restarted, bridge re-verified for Stacy (demographics/diagnoses/claims all return; unknown member errors cleanly). Full table: `data-models.md` §Master verification. | `clearlink/` |

## Doc≠impl drift (see patterns-and-decisions.md for full table)

6 vs 23 detectors · `AI-CLAUDE-V1` vs `CG-BASIC-V1` · likelihood in analyze.py vs case_creation_service.py · migrations auto-run vs disabled · ports 8000/5173 vs 8001/5174 · priority 0.40/0.40/0.20 vs 0.60/0.35/0.05.

## Merger completion backlog (ClaimGuard → OPA)

Phase 2 (frontend re-point) + Phase 3 (delete `claimguard/backend/`) outstanding. Full list in `projects/claimguard.md` MERGER_TODO. Highlights: fix export modals, port denial/approval/messages/evidence endpoints, comments→case_notes, `/config`→`/api/runtime-config`, UUID switch, delete dead backend + authService.ts.
